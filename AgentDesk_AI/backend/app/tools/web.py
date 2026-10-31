"""Bounded website downloads for AgentDesk AI."""
from __future__ import annotations

import ipaddress
import json
import re
import socket
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import httpx
from pydantic import BaseModel, Field, field_validator

from ..security.paths import resolve_within_allowed
from ..verification import failed_result, file_evidence, verdict
from .base import BaseTool, RiskLevel, ToolContext, ToolResult, Verification

MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
MAX_REDIRECTS = 5


def _validate_public_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Only public http:// or https:// website URLs are supported")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing user credentials are not allowed")
    if parsed.port not in (None, 80, 443):
        raise ValueError("Non-standard URL ports are not allowed")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Local and internal network hosts are not allowed")
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(result[4][0])
                for result in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
            }
        except OSError as exc:
            raise ValueError(f"Could not resolve website host: {exc}") from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("Local, private, and reserved network addresses are not allowed")


def _require_public_peer(response) -> None:
    """Defence against DNS rebinding: the hostname was validated by a separate lookup,
    so also check the address the socket actually connected to. No response body is
    read or saved if it was a private/local address. (A GET request has already been
    sent by then, so this limits data exposure, not the request itself.)"""
    stream = (getattr(response, "extensions", None) or {}).get("network_stream")  # real httpx responses always carry extensions
    getter = getattr(stream, "get_extra_info", None)
    if getter is None:
        return
    peer = getter("server_addr")
    if not peer:
        return
    try:
        address = ipaddress.ip_address(str(peer[0]).split("%", 1)[0])
    except ValueError as exc:
        raise ValueError("Connected to an unrecognised network address; download refused") from exc
    if not address.is_global:
        raise ValueError("The connection reached a private or local network address; download refused")


class DownloadWebContentArgs(BaseModel):
    url: str = Field(description="Direct URL of a file or public webpage (no YouTube/video extraction)")
    output_path: str | None = Field(default=None, description="Absolute destination path inside an allowed directory")
    save_as_webpage: bool = Field(default=False, description="Save an HTML webpage instead of a direct file")

    @field_validator("url")
    @classmethod
    def _url_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("url must not be blank")
        return value


class DownloadWebContentTool(BaseTool):
    name = "download_web_content"
    description = (
        "Download a public direct file URL or save a public webpage as HTML into an allowed directory. "
        "Maximum 20 MB; private/local hosts and video extraction are blocked. Requires approval."
    )
    risk_level = RiskLevel.HIGH
    args_schema = DownloadWebContentArgs
    timeout_seconds = 180
    interruptible = True  # pause keeps the .part file; Resume continues with an HTTP Range request

    @staticmethod
    def _safe_filename(value: str) -> str:
        name = Path(value.replace("\\", "/")).name
        name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")
        return name[:180] or "download"

    def _destination(self, args: DownloadWebContentArgs, url: str) -> Path:
        if args.output_path:
            return resolve_within_allowed(args.output_path, self.ctx.allowed_directories)
        parsed = urlsplit(url)
        filename = unquote(Path(parsed.path).name)
        if args.save_as_webpage:
            filename = f"{Path(filename).stem or 'webpage'}.html"
        filename = self._safe_filename(filename)
        if not self.ctx.allowed_directories:
            raise ValueError("No allowed directory is configured for downloads")
        return resolve_within_allowed(
            str(self.ctx.allowed_directories[0] / "Downloads" / filename),
            self.ctx.allowed_directories,
        )

    @staticmethod
    def _partial_paths(destination: Path) -> tuple[Path, Path]:
        """Fixed names so a paused download can be found again and resumed."""
        part = destination.with_name(f".{destination.name}.agentdesk.part")
        return part, part.with_name(part.name + ".json")

    def on_cancel(self, args: BaseModel) -> None:
        a = DownloadWebContentArgs.model_validate(args.model_dump())
        try:
            destination = self._destination(a, a.url)
        except ValueError:
            return
        for path in self._partial_paths(destination):
            path.unlink(missing_ok=True)

    def execute(self, args: BaseModel) -> ToolResult:
        try:
            a = DownloadWebContentArgs.model_validate(args.model_dump())
            current_url = a.url
            _validate_public_url(current_url)
            destination = self._destination(a, current_url)
        except (ValueError, httpx.InvalidURL) as exc:
            return ToolResult(success=False, error=f"Invalid download request: {exc}")
        if destination.exists():
            return ToolResult(success=False, error=f"Destination already exists (not overwritten): {destination}")

        part, meta_path = self._partial_paths(destination)
        resume_from, meta = 0, {}
        if part.exists() and meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                meta = {}
            if meta.get("url") == a.url and meta.get("save_as_webpage") == a.save_as_webpage:
                resume_from = part.stat().st_size
            else:
                meta = {}
        if not resume_from:
            part.unlink(missing_ok=True)
            meta_path.unlink(missing_ok=True)
        keep_partial = False  # only a network interruption keeps the partial file for Resume
        written = 0
        content_type = ""
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            headers = {"User-Agent": "AgentDeskAI/1.0"}
            if resume_from:
                headers["Range"] = f"bytes={resume_from}-"
                validator = meta.get("etag") or meta.get("last_modified")
                if validator:
                    headers["If-Range"] = validator
            with httpx.Client(timeout=20, follow_redirects=False) as client:
                for redirect_count in range(MAX_REDIRECTS + 1):
                    _validate_public_url(current_url)
                    with client.stream("GET", current_url, headers=headers) as response:
                        _require_public_peer(response)
                        if response.status_code in (301, 302, 303, 307, 308):
                            location = response.headers.get("location")
                            if not location or redirect_count == MAX_REDIRECTS:
                                return ToolResult(success=False, error="Website redirect limit exceeded or Location is missing")
                            current_url = urljoin(current_url, location)
                            _validate_public_url(current_url)
                            continue
                        if response.status_code == 416 and resume_from:
                            # The saved part no longer fits the file; start over next time.
                            return ToolResult(success=False, error="The website no longer accepts the saved partial download; retry to start again.")
                        response.raise_for_status()
                        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                        if a.save_as_webpage and content_type != "text/html":
                            return ToolResult(success=False, error=f"Expected an HTML page, received {content_type or 'unknown content'}")
                        if not a.save_as_webpage and content_type == "text/html":
                            return ToolResult(
                                success=False,
                                error="URL returned a webpage; set save_as_webpage=true to save it as HTML",
                            )
                        appending = resume_from > 0 and response.status_code == 206 and \
                            response.headers.get("content-range", "").startswith(f"bytes {resume_from}-")
                        if not appending:
                            resume_from = 0  # server ignored Range or the file changed: start over
                        length = response.headers.get("content-length")
                        if length and resume_from + int(length) > MAX_DOWNLOAD_BYTES:
                            return ToolResult(success=False, error="Download exceeds the 20 MB size limit")
                        meta_path.write_text(json.dumps({
                            "url": a.url, "save_as_webpage": a.save_as_webpage, "content_type": content_type,
                            "etag": response.headers.get("etag"), "last_modified": response.headers.get("last-modified"),
                        }), encoding="utf-8")
                        written = resume_from
                        keep_partial = True
                        with part.open("ab" if appending else "wb") as output:
                            for chunk in response.iter_bytes():
                                written += len(chunk)
                                if written > MAX_DOWNLOAD_BYTES:
                                    keep_partial = False
                                    return ToolResult(success=False, error="Download exceeds the 20 MB size limit")
                                output.write(chunk)
                                output.flush()
                        if written == 0:
                            keep_partial = False
                            return ToolResult(success=False, error="The website returned an empty response")
                        break
                else:
                    return ToolResult(success=False, error="Website redirect limit exceeded")
            if a.save_as_webpage and destination.suffix.lower() not in (".html", ".htm"):
                destination = destination.with_suffix(".html")
                if destination.exists():
                    keep_partial = False
                    return ToolResult(success=False, error=f"Destination already exists (not overwritten): {destination}")
            part.replace(destination)
            keep_partial = False
        except (httpx.HTTPError, OSError) as exc:
            saved = part.stat().st_size if part.exists() else 0
            note = f" {saved} bytes are kept; Resume continues from there." if keep_partial and saved else ""
            return ToolResult(success=False, output={"partial_bytes": saved if keep_partial else 0},
                              error=f"Could not download website content: {exc}.{note}")
        except ValueError as exc:
            keep_partial = False
            return ToolResult(success=False, error=f"Could not download website content: {exc}")
        finally:
            if not keep_partial:
                part.unlink(missing_ok=True)
                meta_path.unlink(missing_ok=True)
        return ToolResult(
            success=True,
            output={"path": str(destination), "url": current_url, "bytes_written": written,
                    "resumed_from": resume_from, "content_type": content_type},
        )

    def verify(self, args: BaseModel, result: ToolResult) -> Verification:
        if not result.success:
            return failed_result(result)
        target = Path(result.output["path"])
        evidence = file_evidence(target)
        return verdict([("download saved with expected size", evidence.get("size") == result.output["bytes_written"])],
                       {**evidence, "url": result.output.get("url")})

def web_tools(ctx: ToolContext | None = None) -> list[BaseTool]:
    return [DownloadWebContentTool(ctx)]


