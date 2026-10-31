"""Build the Windows release zip.

    python packaging/build_release.py [--out DIR]

The zip contains the app source, the prebuilt frontend (frontend/dist), the browser
extension, user docs, the pinned requirements, START_AGENT_X.cmd and the installer.
It never contains: .env files, databases, logs, tokens, virtual environments,
node_modules, tests or git data. A manifest with SHA-256 hashes is added, and the
build refuses to produce a zip if a forbidden file or a secret-shaped string is found.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]  # .../AgentDesk_AI
REPO = PROJECT.parent  # contains START_AGENT_X.cmd
PACKAGE_DIR = "AgentDesk-AI"

# (source root, glob, optional exclude substrings)
INCLUDE = [
    (REPO, "START_AGENT_X.cmd", ()),
    (REPO, "START_AGENT_X_DESKTOP.cmd", ()),
    (PROJECT / "desktop", "*.py", ()),
    (PROJECT / "packaging", "INSTALL.cmd", ()),
    (PROJECT / "packaging", "install.ps1", ()),
    (PROJECT / "packaging", "README-INSTALL.txt", ()),
    (PROJECT, "launch.py", ()),
    (PROJECT, ".env.example", ()),
    (PROJECT / "backend", "app/**/*.py", ()),
    (PROJECT / "backend", "run_server.py", ()),
    (PROJECT / "backend", "requirements.txt", ()),
    (PROJECT / "backend", "requirements.lock.txt", ()),
    (PROJECT / "backend", "requirements-desktop.txt", ()),
    (PROJECT / "browser-extension", "*.js", ()),
    (PROJECT / "browser-extension", "*.json", ()),
    (PROJECT / "browser-extension", "*.html", ()),
    (PROJECT / "docs", "*.md", ()),
    (PROJECT / "docs", "audit/**/*.md", ()),
    (PROJECT / "frontend", "dist/**/*", ()),
]
FORBIDDEN = re.compile(r"(^|/)(\.env($|\.)|.*\.(db|sqlite3?|log|pem|key|pfx)$|api_token$|.*\.venv.*|node_modules|__pycache__|\.git)(/|$)", re.I)
SECRET = re.compile(r"gsk_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{30,}|AIza[0-9A-Za-z_-]{30,}")


def version() -> str:
    text = (PROJECT / "backend" / "app" / "config.py").read_text(encoding="utf-8")
    match = re.search(r'app_version: str = "([^"]+)"', text)
    return match.group(1) if match else "0.0.0"


def collect() -> list[tuple[Path, str]]:
    seen: dict[str, Path] = {}
    for root, pattern, _ in INCLUDE:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                if root == REPO:
                    arcname = path.name
                elif root == PROJECT / "packaging":
                    arcname = path.name
                else:
                    arcname = "AgentDesk_AI/" + path.relative_to(PROJECT).as_posix()
                seen[arcname] = path
    return sorted(((p, a) for a, p in seen.items()), key=lambda item: item[1])


def check(files: list[tuple[Path, str]]) -> list[str]:
    problems = []
    names = {arc for _, arc in files}
    for required in ("START_AGENT_X.cmd", "INSTALL.cmd", "install.ps1", "AgentDesk_AI/launch.py", "AgentDesk_AI/backend/run_server.py",
                     "AgentDesk_AI/backend/requirements.lock.txt", "AgentDesk_AI/frontend/dist/index.html", "AgentDesk_AI/backend/app/main.py"):
        if required not in names:
            problems.append(f"missing required file: {required} (build the frontend with `npm run build` first?)")
    for path, arc in files:
        if FORBIDDEN.search(arc) and not arc.endswith(".env.example"):
            problems.append(f"forbidden file in package: {arc}")
        if path.suffix.lower() in {".js", ".json", ".html", ".md", ".py", ".txt", ".cmd", ".ps1", ".css", ".svg", ".example"} or path.name == ".env.example":
            if SECRET.search(path.read_text(encoding="utf-8", errors="ignore")):
                problems.append(f"secret-shaped string in {arc}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(PROJECT / "dist-release"))
    args = parser.parse_args()
    files = collect()
    problems = check(files)
    if problems:
        print("Refusing to build:\n  " + "\n  ".join(problems))
        return 1
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    name = f"AgentDesk-AI-{version()}-win"
    target = out / f"{name}.zip"
    manifest = []
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, arc in files:
            data = path.read_bytes()
            if path.suffix.lower() in {".cmd", ".ps1", ".txt"}:
                data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")  # Windows line endings for scripts
            archive.writestr(f"{PACKAGE_DIR}/{arc}", data)
            manifest.append(f"{hashlib.sha256(data).hexdigest()}  {arc}")
        archive.writestr(f"{PACKAGE_DIR}/VERSION", version() + "\r\n")
        archive.writestr(f"{PACKAGE_DIR}/MANIFEST.sha256", "\r\n".join(manifest) + "\r\n")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (out / f"{name}.zip.sha256").write_text(f"{digest}  {target.name}\n", encoding="utf-8")
    print(f"Built {target} ({target.stat().st_size / 1024:.0f} KB, {len(files)} files)\nSHA-256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
