#!/usr/bin/env python3
"""
PreToolUse hook: block obviously dangerous shell commands and any attempt to
read/print secret files.

Hook contract (Claude Code):
- Reads a JSON event from stdin.
- Looks at the tool name and its `command` argument when the tool is Bash / PowerShell / shell-like.
- Exits 2 to BLOCK the call. The message printed on stderr is shown back to the assistant.
- Exits 0 to allow the call.

This script is intentionally conservative. It is meant to catch obvious mistakes,
not to be a security boundary. The real security boundary is the human reviewer.
"""

from __future__ import annotations

import json
import re
import sys

# ---- Patterns -------------------------------------------------------------

# Each entry: (compiled regex, short reason shown to the assistant)
DANGEROUS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)\b"),
        "`rm -rf` (or equivalent) is blocked. It is hard to reverse. "
        "If you really need to delete something, delete it more narrowly "
        "or ask the human to do it.",
    ),
    (
        # Separate flags / long options: `rm -r -f`, `rm --recursive --force`
        # (the combined `-rf` form is caught by the pattern above).
        re.compile(
            r"\brm\b(?=[^|;&\n]*\s-(?:[rR]|-recursive)\b)"
            r"(?=[^|;&\n]*\s-(?:f|-force)\b)"
        ),
        "`rm` with recursive + force flags is blocked, however they are spelled. "
        "Delete more narrowly or ask the human.",
    ),
    (
        re.compile(r"\bfind\b[^|;&\n]*\s-delete\b"),
        "`find ... -delete` is blocked. It bulk-deletes matched files with no undo. "
        "Narrow the deletion or ask the human.",
    ),
    # PowerShell / cmd destructive deletes. The Unix `rm -rf` patterns above do
    # not cover these, and on Windows this is the real hazard.
    (
        re.compile(
            r"(?i)\b(?:Remove-Item|rm|ri|rd|rmdir|del|erase)\b"
            r"(?=[^|;&\n]*\s-(?:Recurse|rec|r)\b)"
            r"(?=[^|;&\n]*\s-(?:Force|fo|f)\b)"
        ),
        "PowerShell recursive+force delete (e.g. `Remove-Item -Recurse -Force`) is "
        "blocked. Delete more narrowly or ask the human.",
    ),
    (
        re.compile(r"(?i)\b(?:rd|rmdir|del|erase)\b[^|;&\n]*\s/[sq]\b"),
        "cmd-style recursive/quiet delete (`/s` `/q`) is blocked.",
    ),
    (
        re.compile(r"(?i)\bClear-Content\b"),
        "`Clear-Content` is blocked. It empties a file's contents in place with no "
        "undo. Edit the file narrowly or ask the human.",
    ),
    (
        re.compile(r"\bgit\s+reset\s+--hard\b"),
        "`git reset --hard` is blocked. It silently destroys uncommitted work. "
        "Use `git stash` or a narrower revert instead, or ask the human.",
    ),
    (
        re.compile(r"\bgit\s+clean\s+-[a-zA-Z]*f"),
        "`git clean -f` family is blocked. It permanently deletes untracked files "
        "that may be in-progress work. Ask the human before cleaning the tree.",
    ),
    (
        re.compile(r"\bgit\s+push\b[^|;&\n]*--force(?!-with-lease)"),
        "`git push --force` is blocked (use `--force-with-lease` if a force push "
        "is truly needed, and only after the human approves).",
    ),
    (
        re.compile(r"\bgit\s+branch\s+-D\b"),
        "`git branch -D` is blocked. It force-deletes a branch even with unmerged "
        "work. Use `git branch -d` for a safe delete, or ask the human.",
    ),
    # Secret-file access patterns. We block reading/printing the file contents
    # rather than the existence check (`ls`, `Test-Path`, `stat`).
    (
        re.compile(
            r"(?i)\b(cat|type|bat|less|more|head|tail|nl|xxd|od|strings|"
            r"grep|egrep|fgrep|rg|sort|awk|sed|"
            r"Get-Content|gc|Select-String|sls)\b[^|;&\n]*\.env(\.[A-Za-z0-9_.-]+)?\b"
        ),
        "Reading `.env` (or `.env.*`) is blocked. These files hold secrets. "
        "If you need to know which variables exist, look at `.env.example` instead.",
    ),
    (
        re.compile(
            r"(?i)\b(cat|type|bat|less|more|head|tail|strings|"
            r"grep|egrep|fgrep|rg|sort|awk|sed|"
            r"Get-Content|gc|Select-String|sls)\b[^|;&\n]*\.(pem|key|p12|pfx)\b"
        ),
        "Reading private-key files (.pem / .key / .p12 / .pfx) is blocked. "
        "These are credentials.",
    ),
    (
        re.compile(
            r"\b(echo|printf|Write-Host|Write-Output)\b[^|;&\n]*\$\{?"
            r"(SECRET|TOKEN|PASSWORD|API_KEY|PRIVATE_KEY|AWS_SECRET_ACCESS_KEY|"
            r"GITHUB_TOKEN|OPENAI_API_KEY|ANTHROPIC_API_KEY)"
        ),
        "Printing a secret-looking environment variable is blocked. "
        "If you need to confirm a variable is set, check its length, not its value.",
    ),
    (
        re.compile(r"\$env:(SECRET|TOKEN|PASSWORD|API_KEY|PRIVATE_KEY)\b"),
        "Printing a secret-looking environment variable is blocked.",
    ),
]


def extract_command(event: dict) -> str | None:
    """
    Pull the command string out of the hook event, regardless of which shell
    tool is in use. Returns None if this is not a shell-tool call.
    """
    tool_name = (event.get("tool_name") or event.get("tool") or "").lower()
    tool_input = event.get("tool_input") or event.get("input") or {}

    if tool_name in {"bash", "powershell", "shell", "sh"}:
        cmd = tool_input.get("command")
        if isinstance(cmd, str):
            return cmd
    return None


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        # Don't block on malformed events; just let the call through.
        return 0

    command = extract_command(event)
    if not command:
        return 0

    for pattern, reason in DANGEROUS_PATTERNS:
        if pattern.search(command):
            print(reason, file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
