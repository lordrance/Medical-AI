"""
================================================================================
文件作用：读取和填充「提示词模板」
================================================================================

调用 AI 时要给它两段话：
    系统提示（system）  设定它的身份和规则，比如"你是一位医学研究助理"
    用户提示（user）    具体让它干什么，比如"请总结下面这批数据"

这两段话没有写死在代码里，而是放在同目录下的 .md 文件里。

★ 为什么单独放文件：提示词是需要反复调整措辞的内容，而且它直接影响
  研究结论。放在 .md 文件里，改动在 git 里有清晰的历史记录，
  审稿时能拿得出"当时用的到底是哪一版提示词"。

.md 文件的格式约定：

    # [SYSTEM]
    你是一位医学研究助理……

    # [USER]
    请总结下面这批数据：
    {{data}}

其中 {{data}} 是占位符，运行时会被真实数据替换掉。

--------------------------------------------------------------------------------
本文件的代码块（从上到下）：
--------------------------------------------------------------------------------
  第 1 块  PROMPTS_DIR / _SECTION_RE  文件位置和分节的正则
  第 2 块  load_prompt()              读一个模板文件，拆成两段
  第 3 块  render_template()          把占位符换成真实内容
================================================================================
"""

from __future__ import annotations

import re
from pathlib import Path


# ── 第 1 块：文件位置和分节规则 ────────────────────────────────────────────
# 提示词文件就放在本文件所在的目录里。
# __file__ 是本文件的路径，.parent 取它所在的文件夹。
# 用相对定位而不是写死绝对路径，本机和 Docker 容器里都能跑。
PROMPTS_DIR = Path(__file__).resolve().parent

# 匹配 "# [SYSTEM]" 或 "# [USER]" 这样的分节标题。
#   ^ 和 $        表示这一行的开头和结尾
#   \s*           允许标题后面有多余的空格
#   re.MULTILINE  让 ^ $ 匹配每一行，而不是整个文件的首尾
# 括号 (SYSTEM|USER) 是「捕获组」——分割时会把括号里的内容也保留下来，
# 下面就是靠这个知道每一段属于哪一节的。
_SECTION_RE = re.compile(r"^# \[(SYSTEM|USER)\]\s*$", re.MULTILINE)


# ── 第 2 块：读取模板文件 ──────────────────────────────────────────────────
def load_prompt(name: str) -> tuple[str, str]:
    """Load prompt from `<name>.md`. Returns (system, user_template).

    The file must contain `# [SYSTEM]` and `# [USER]` headers exactly once each.

    中文：读一个提示词文件，拆成"系统提示"和"用户提示模板"两段返回。
    传的 name 不带扩展名，比如 load_prompt("cohort_summary")。
    """
    path = PROMPTS_DIR / f"{name}.md"
    # 必须指定 utf-8，否则 Windows 上读中文提示词会乱码。
    text = path.read_text(encoding="utf-8")

    # 按分节标题切开。因为正则里有捕获组，切出来的结果是交替的：
    #   [标题前的内容, "SYSTEM", SYSTEM 的正文, "USER", USER 的正文]
    parts = _SECTION_RE.split(text)

    # Split returns: [pre, header1, body1, header2, body2, ...]
    # 从下标 1 开始，每次跳两格：拿一个标题、拿一段正文，配成一对。
    sections: dict[str, str] = {}
    i = 1
    while i < len(parts):
        header = parts[i]
        # 防御性写法：万一文件最后只有标题没有正文，不至于下标越界。
        body = parts[i + 1] if i + 1 < len(parts) else ""
        sections[header] = body.strip()   # strip 去掉首尾多余的空行
        i += 2

    # 两节缺一不可。缺了就明确报错，而不是拿着半个提示词去调 AI——
    # 那样 AI 会返回一段莫名其妙的内容，而你很难想到是提示词文件写错了。
    if "SYSTEM" not in sections or "USER" not in sections:
        raise ValueError(f"prompt file {path} missing SYSTEM/USER sections")
    return sections["SYSTEM"], sections["USER"]


# ── 第 3 块：填充占位符 ────────────────────────────────────────────────────
def render_template(template: str, variables: dict[str, str]) -> str:
    """把模板里的 {{键名}} 替换成真实内容。

    例：render_template("总结：{{data}}", {"data": "..."})

    ★ 为什么用最朴素的字符串替换，而不用 Python 自带的 format()：
      提示词里经常出现大括号（比如让 AI 输出 JSON 格式的例子），
      format() 会把那些大括号当成占位符而报错。用 {{双大括号}} 加
      手工替换，就不会和正文里的单大括号打架。
    """
    out = template
    for k, v in variables.items():
        out = out.replace("{{" + k + "}}", v)
    return out
