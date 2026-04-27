from __future__ import annotations

import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent

_SECTION_RE = re.compile(r"^# \[(SYSTEM|USER)\]\s*$", re.MULTILINE)


def load_prompt(name: str) -> tuple[str, str]:
    """Load prompt from `<name>.md`. Returns (system, user_template).

    The file must contain `# [SYSTEM]` and `# [USER]` headers exactly once each.
    """
    path = PROMPTS_DIR / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    parts = _SECTION_RE.split(text)
    # Split returns: [pre, header1, body1, header2, body2, ...]
    sections: dict[str, str] = {}
    i = 1
    while i < len(parts):
        header = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        sections[header] = body.strip()
        i += 2
    if "SYSTEM" not in sections or "USER" not in sections:
        raise ValueError(f"prompt file {path} missing SYSTEM/USER sections")
    return sections["SYSTEM"], sections["USER"]


def render_template(template: str, variables: dict[str, str]) -> str:
    out = template
    for k, v in variables.items():
        out = out.replace("{{" + k + "}}", v)
    return out
