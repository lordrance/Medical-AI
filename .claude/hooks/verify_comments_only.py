"""PostToolUse hook: 每次改完源码文件，自动检查「有没有把代码改坏」。

背景
----
给代码加中文注释时要整文件重写，手滑改坏一行代码是真实风险。本项目已经
被咬过两次：一次删掉了数据库关联字段（35 个测试当场挂掉），一次把一行
字段定义写了两遍（Pydantic 静默接受，86 个测试全绿，测试根本发现不了）。

scripts/verify_code_unchanged.py 能查出这类问题，但前提是「记得跑」。
这个钩子把它变成自动的。

行为
----
  * 只在改动 backend/app、backend/tests、backend/alembic、frontend/src
    下的 .py / .ts / .tsx 时才触发，改别的文件直接跳过；
  * 校验通过 → 什么都不输出，不打扰；
  * 校验失败 → 输出一段 JSON，同时提醒用户、把详情送回模型上下文。

它只提醒、不拦截：真要改代码时报一下是正常的，不该挡住工作。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# 仓库根目录 = 本文件往上三级（.claude/hooks/x.py → .claude/hooks → .claude → 根）
REPO = Path(__file__).resolve().parents[2]

# 只关心这几个目录下的源码。路径统一用正斜杠比较，避免 Windows 反斜杠的麻烦。
WATCHED = ("backend/app/", "backend/tests/", "backend/alembic/", "frontend/src/")
EXTS = (".py", ".ts", ".tsx")


def main() -> int:
    # 钩子的输入是一段 JSON，从标准输入进来。读不到或格式不对就安静退出——
    # 钩子自己出问题绝不能影响正常工作。
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    # 被改动的文件路径。Write 和 Edit 的字段位置略有不同，两个都试。
    tool_input = payload.get("tool_input") or {}
    tool_response = payload.get("tool_response") or {}
    path = tool_input.get("file_path") or tool_response.get("filePath") or ""
    path = str(path).replace("\\", "/")

    # 不是我们关心的文件就跳过，省得每次写临时文件都跑一遍。
    if not path.endswith(EXTS) or not any(w in path for w in WATCHED):
        return 0

    # 跑真正的校验脚本。cwd 指到仓库根目录，因为它内部要调 git。
    try:
        proc = subprocess.run(
            [sys.executable, "scripts/verify_code_unchanged.py"],
            cwd=REPO,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except Exception:
        return 0  # 脚本跑不起来也不要打断工作

    out = (proc.stdout or "") + (proc.stderr or "")
    if "FAIL" not in out:
        return 0  # 通过，安静退出

    # 失败了：告诉用户，同时把详情塞回模型的上下文里，让它当场修。
    #
    # ★ ensure_ascii=True（默认）不能省：Windows 控制台默认是 GBK 编码，
    # 直接打印中文或 ⚠ 这类字符会抛 UnicodeEncodeError，钩子当场崩掉、
    # 警告也就发不出来了（这个坑已经踩过一次）。
    # 转成 \uXXXX 转义后输出的全是 ASCII 字节，读取方解析 JSON 时会还原成中文。
    payload_out = json.dumps(
        {
            "systemMessage": "[!] 代码校验未通过：这次改动动到了代码，不只是注释",
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": (
                    "verify_code_unchanged.py 报告代码发生了变化（本应只改注释）。\n"
                    "请对照下面的输出检查刚才写的文件，把被改动的代码改回去：\n\n"
                    + out.strip()
                ),
            },
        }
    )
    # 再保险一层：万一输出通道还是不认，也不要让钩子崩掉。
    try:
        sys.stdout.write(payload_out + "\n")
    except Exception:
        sys.stdout.buffer.write(payload_out.encode("utf-8", "replace") + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
