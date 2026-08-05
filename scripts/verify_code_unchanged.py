"""确认「只改了注释、没动代码」的验证工具。

给代码加注释时，最大的风险是手滑删掉一行代码——这种错误看起来无害，
测试却不一定能覆盖到（本项目就发生过一次：加注释时误删了一个数据库
关联字段，导致 35 个测试挂掉）。

这个脚本把每个改动过的文件和 git 里的版本做对比，剥掉注释之后比较剩下的
纯代码：
  * Python 用官方 tokenize 模块做词法分析，逐个 token 比对，最严格；
  * TypeScript / TSX 没有内置词法器，退而求其次——去掉注释后检查
    有没有哪一行代码凭空消失了。

用法：
    python scripts/verify_code_unchanged.py            # 对比工作区 vs HEAD
    python scripts/verify_code_unchanged.py HEAD~3     # 对比工作区 vs 三个提交前

代码有变化时返回非零退出码，方便挂进 CI 或提交前钩子。
"""

from __future__ import annotations

import io
import re
import subprocess
import sys
import tokenize

# 只检查这些目录，不看 node_modules、构建产物之类的。
WATCHED = ("backend/app", "backend/tests", "backend/alembic", "frontend/src")


def _git(args: list[str]) -> str:
    """跑一条 git 命令并返回它的输出。

    errors="replace" 很重要：仓库里有中文注释，遇到解码不了的字节时
    用替代字符顶上，而不是直接抛异常中断整个检查。
    """
    return subprocess.run(
        args, capture_output=True, encoding="utf-8", errors="replace"
    ).stdout


def python_tokens(src: str) -> list[str]:
    """把一段 Python 源码变成「去掉注释后的 token 列表」。

    token（词元）就是代码被拆成的最小单位：变量名、括号、运算符……
    只要两个版本的 token 列表一模一样，就能确定代码逻辑没有任何改动，
    哪怕缩进、换行、空格全变了也不影响判断。
    """
    out: list[str] = []
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except Exception:
        # 语法不完整（比如文件正在编辑中）时退回按行比较，不让脚本崩掉。
        return [ln.strip() for ln in src.splitlines() if ln.strip()]

    prev = tokenize.INDENT
    for t in toks:
        if t.type == tokenize.COMMENT:
            continue  # 丢弃 # 开头的注释
        # 文档字符串：出现在语句开头位置的孤立字符串。它也是注释，要丢掉。
        if t.type == tokenize.STRING and prev in (
            tokenize.INDENT,
            tokenize.NEWLINE,
            tokenize.NL,
            tokenize.DEDENT,
        ):
            continue
        # 换行、缩进这些排版类 token 不参与比较，只留真正的代码。
        if t.type not in (
            tokenize.NL,
            tokenize.NEWLINE,
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.ENDMARKER,
        ):
            out.append(t.string)
        if t.type not in (tokenize.NL, tokenize.COMMENT):
            prev = t.type
    return out


def ts_code_lines(src: str) -> list[str]:
    """把一段 TypeScript 源码变成「去掉注释后的代码行列表」。"""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)  # 去掉 /* */ 和 {/* */} 块注释
    out: list[str] = []
    for line in src.splitlines():
        # 去掉 // 行注释。前面的 (?<!:) 是为了别把 https:// 里的双斜杠也当成注释。
        line = re.sub(r"(?<!:)//.*$", "", line).strip()
        if line and line not in ("{", "}"):  # 空行和孤立的花括号不比较
            out.append(re.sub(r"\s+", " ", line))  # 多个空格压成一个，忽略排版差异
    return out


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "HEAD"
    changed = _git(["git", "diff", "--name-only", base, "--", *WATCHED]).split()

    py = [f for f in changed if f.endswith(".py")]
    ts = [f for f in changed if f.endswith((".ts", ".tsx"))]
    problems: list[str] = []

    # ---- Python：逐 token 比对 ----
    for f in py:
        old = python_tokens(_git(["git", "show", f"{base}:{f}"]))
        new = python_tokens(open(f, encoding="utf-8").read())
        if old != new:
            problems.append(f"{f}: token stream differs ({len(old)} -> {len(new)})")

    # ---- TypeScript：检查有没有代码行消失 ----
    for f in ts:
        old = ts_code_lines(_git(["git", "show", f"{base}:{f}"]))
        new = ts_code_lines(open(f, encoding="utf-8").read())
        # 只查「原来有、现在没了」的行。新增行是正常的（比如把一行拆成多行）。
        removed = [ln for ln in old if ln not in new]
        if removed:
            problems.append(f"{f}: {len(removed)} code line(s) removed, e.g. {removed[0][:70]}")

    print(f"checked {len(py)} python + {len(ts)} ts/tsx files against {base}")
    if problems:
        for p in problems:
            print("  FAIL " + p)
        return 1
    print("OK: comments only, no code changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
