"""Deterministic mock AI provider for tests and offline development.

Clearly labelled: every Plan it returns has mock=True. It understands a
fixed set of command patterns; anything else yields a clarification note.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from .base import AIProvider, Plan, PlanAction


class MockProvider(AIProvider):
    name = "mock"
    is_mock = True

    def __init__(self, home: Path | None = None) -> None:
        if home is None:
            # AGENTDESK_MOCK_HOME lets tests redirect "Documents"/"Downloads".
            home = Path(os.environ.get("AGENTDESK_MOCK_HOME", str(Path.home())))
        self.home = Path(home)

    def _act(self, tool: str, args: dict, rationale: str) -> PlanAction:
        return PlanAction(tool=tool, args=args, rationale=rationale)

    def generate_plan(self, command: str, tool_descriptions: str) -> Plan:
        cmd = command.strip()
        docs = str(self.home / "Documents")
        dl = str(self.home / "Downloads")

        def plan(*actions: PlanAction) -> Plan:
            return Plan(actions=list(actions), mock=True)

        def clarify(question: str) -> Plan:
            return Plan(actions=[], note=question, mock=True)

        # --- meta: previous task -------------------------------------------------
        if re.search(r"show (the )?result of (the )?previous task", cmd, re.IGNORECASE):
            return Plan(actions=[], note="__PREVIOUS_TASK__", mock=True)

        # --- open application ----------------------------------------------------
        if re.fullmatch(r"open (?:the )?(?:email|e-mail|mail)(?: app| client)?[.!]?", cmd, re.IGNORECASE):
            return plan(self._act("open_application", {"app_name": "mail"}, "Open the default email app"))

        m = re.search(r"open (?:the )?app(?:lication)? ([\w\-. ]+)", cmd, re.IGNORECASE)
        if m:
            app = m.group(1).strip()
            return plan(self._act("open_application", {"app_name": app}, f"Launch {app}"))
        # "Open Chrome." style: bare known application name
        from ..tools.apps import APP_TARGETS

        m = re.match(r"open (?:the )?([\w\-. ]+?)[.!]?$", cmd, re.IGNORECASE)
        if m and m.group(1).strip().lower() in APP_TARGETS:
            app = m.group(1).strip()
            return plan(self._act("open_application", {"app_name": app}, f"Launch {app}"))

        # --- open well-known folders ---------------------------------------------
        if re.search(r"open (?:my )?downloads folder", cmd, re.IGNORECASE):
            return plan(self._act("open_folder", {"path": dl}, "Open the Downloads folder"))
        if re.search(r"open (?:my )?documents folder", cmd, re.IGNORECASE):
            return plan(self._act("open_folder", {"path": docs}, "Open the Documents folder"))

        # --- copy ------------------------------------------------------------------
        m = re.search(r"copy (?:the )?(?:file|folder) (.+?) to (.+)", cmd, re.IGNORECASE)
        if m:
            source, destination = m.group(1).strip().strip('"'), m.group(2).strip().strip('"')
            if Path(source).is_absolute() and Path(destination).is_absolute():
                return plan(
                    self._act(
                        "copy_file",
                        {"source": source, "destination": destination},
                        "Copy the file or folder",
                    )
                )
            return clarify("Please give absolute source and destination paths inside allowed directories.")

        # --- draft email ------------------------------------------------------------
        m = re.search(
            r"(?:write|draft|compose) (?:an? )?email to (\S+) with subject (.+?) and body (.+)",
            cmd,
            re.IGNORECASE,
        )
        if m:
            recipient, subject, body = m.group(1), m.group(2).strip(), m.group(3).strip()
            return plan(
                self._act(
                    "compose_email",
                    {"to": recipient, "subject": subject, "body": body},
                    "Prepare an email draft for the user to review",
                )
            )
        if re.search(r"\b(?:write|draft|compose)\b.*\bemail\b", cmd, re.IGNORECASE):
            return clarify("Please provide the recipient email address, subject, and message body.")

        # --- create folder ---------------------------------------------------------
        m = re.search(r"create (?:a )?folder called ([\w\-. ]+?) in (?:my )?documents", cmd, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            return plan(
                self._act("create_folder", {"path": str(Path(docs) / name)}, f"Create folder '{name}' in Documents")
            )
        m = re.search(
            r"create (?:a )?folder (?:called|named|name is) ([\w\-. ]+?) in (?:my )?(?:desktop|destop)",
            cmd,
            re.IGNORECASE,
        )
        if m:
            name = m.group(1).strip()
            desktop = self.home / "Desktop"
            return plan(
                self._act("create_folder", {"path": str(desktop / name)}, f"Create folder '{name}' on Desktop")
            )
        m = re.search(r"create (?:a )?folder (?:called|named) ([\w\-. ]+)", cmd, re.IGNORECASE)
        if m:
            return clarify(
                f"Where should I create the folder '{m.group(1).strip()}'? "
                "Please give me a parent folder, e.g. 'in Documents'."
            )

        # --- list folder ------------------------------------------------------------
        m = re.search(r"(?:list|show)(?: the)? files in (?:my )?(\w+)", cmd, re.IGNORECASE)
        if m:
            where = m.group(1).lower()
            mapping = {"downloads": dl, "documents": docs}
            if where in mapping:
                return plan(self._act("list_folder", {"path": mapping[where]}, f"List {where}"))
            return clarify(f"Which folder do you mean by '{m.group(1)}'? Give me an absolute path.")

        # --- rename ------------------------------------------------------------------
        m = re.search(r"rename (?:the )?(?:file|folder) (.+?) to (.+)", cmd, re.IGNORECASE)
        if m:
            src, new_name = m.group(1).strip(), m.group(2).strip()
            if Path(src).is_absolute():
                return plan(self._act("rename_file", {"path": src, "new_name": new_name}, f"Rename to '{new_name}'"))
            return clarify(f"Which file should I rename? '{src}' is not an absolute path.")
        if re.search(r"\brename\b", cmd, re.IGNORECASE):
            return clarify("What should I rename, and what is the new name? Example: 'Rename the file C:\\Temp\\a.txt to b.txt'.")

        # --- move ---------------------------------------------------------------------
        m = re.search(r"move (?:the )?(?:file|folder) (.+?) (?:in)?to (.+)", cmd, re.IGNORECASE)
        if m:
            src, dst = m.group(1).strip(), m.group(2).strip()
            if Path(src).is_absolute() and Path(dst).is_absolute():
                return plan(self._act("move_file", {"source": src, "destination": dst}, "Move the file"))
            return clarify("Please give me absolute source and destination paths for the move.")
        if re.search(r"\bmove\b", cmd, re.IGNORECASE):
            return clarify("What should I move, and where to? Example: 'Move the file C:\\Temp\\a.txt to C:\\Temp\\Done'.")

        # --- compress -------------------------------------------------------------------
        m = re.search(r"compress (?:the )?folder (.+?)(?: into (?:a )?zip)?$", cmd, re.IGNORECASE)
        if m:
            folder = m.group(1).strip()
            if Path(folder).is_absolute():
                return plan(self._act("compress_folder", {"folder_path": folder}, "Compress into a ZIP archive"))
            return clarify(f"Which folder should I compress? '{folder}' is not an absolute path.")

        # --- extract ---------------------------------------------------------------------
        m = re.search(r"extract (?:the )?(?:zip|archive)(?: file)? (.+)", cmd, re.IGNORECASE)
        if m:
            zp = m.group(1).strip()
            if Path(zp).is_absolute():
                return plan(self._act("extract_file", {"zip_path": zp}, "Extract the archive"))
            return clarify(f"Which archive? '{zp}' is not an absolute path.")

        # --- delete ------------------------------------------------------------------------
        m = re.search(r"delete (?:the )?(?:file|folder) (.+)", cmd, re.IGNORECASE)
        if m:
            target = m.group(1).strip()
            if Path(target).is_absolute():
                return plan(self._act("delete_file", {"path": target}, "Delete (needs explicit approval)"))
            return clarify(f"Which file should I delete? '{target}' is not an absolute path.")

        # --- open website --------------------------------------------------------------------
        m = re.search(r"open (?:the )?(?:website|site|web ?page) (\S+)", cmd, re.IGNORECASE)
        if m:
            url = m.group(1).strip().rstrip(".")
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            return plan(self._act("open_url", {"url": url}, f"Open {url}"))

        # --- screenshot -----------------------------------------------------------------------
        if re.search(r"(take|screenshot|capture)(.*)(screenshot|screen)", cmd, re.IGNORECASE):
            return plan(self._act("take_screenshot", {}, "Capture the screen"))

        return clarify(
            "I don't know how to do that yet with the mock planner. "
            "Try one of: open Chrome, open my Downloads folder, create a folder called FYP in Documents, "
            "open the website example.com, take a screenshot."
        )
