"""确认「只改了注释、没动代码」的验证工具。

给代码加注释时，最大的风险是手滑改坏一行代码——这种错误看起来无害，
测试却不一定能覆盖到。本项目已经被这个问题咬过两次：
  * 一次是重写文件时删掉了一个数据库关联字段，35 个测试当场挂掉；
  * 一次是把 `selectedAction: SelectedAction` 写了两遍，Pydantic 静默接受，
    86 个测试全绿，靠这个脚本才发现。

────────────────────────────────────────────────────────────────────────────
Python 用「语法树（AST）」比对，不是简单比文本
────────────────────────────────────────────────────────────────────────────
最早的版本只比对「去掉注释后的 token 序列」，有个致命盲区：**缩进**。

    def f(x):          def f(x):
        if x:              if x:
            log()              log()
        send()  ← 总是发送        send()  ← 只在出错时发送

这两段的 token 序列一模一样（`def f ( x ) : if x : log ( ) send ( )`），
但行为完全相反。Python 靠缩进决定代码归属，光比 token 看不出来。

所以改成比对语法树：先把源码解析成结构化的树（if 语句下面挂着哪几行、
函数体里有哪些语句，全都在树里），再把文档字符串摘掉，最后比对整棵树。
缩进一变，树的形状就变了，一定会被抓出来。

────────────────────────────────────────────────────────────────────────────
TypeScript 没有内置的语法树工具，用两道检查兜底
────────────────────────────────────────────────────────────────────────────
  1. 有没有代码行**消失**了（删掉或改坏了某行）
  2. 有没有代码行**凭空多出来**（写重复了、多打了一行）
只加注释的话这两项都应该是零。

用法：
    python scripts/verify_code_unchanged.py            # 工作区 vs HEAD
    python scripts/verify_code_unchanged.py HEAD~3     # 工作区 vs 三个提交前

发现代码有变化时返回非零退出码，方便挂进 CI 或提交前钩子。
"""

from __future__ import annotations

import ast
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


# ── Python：语法树比对 ──────────────────────────────────────────────────────


def _strip_docstrings(tree: ast.AST) -> ast.AST:
    """把文档字符串从语法树里摘掉。

    文档字符串（写在函数/类/文件开头的那段三引号文字）本质上也是注释，
    只是 Python 把它当成一条语句放进了语法树。不摘掉的话，
    改文档字符串会被误判成「改了代码」。
    """
    for node in ast.walk(tree):
        # 只有这四种节点才可能带文档字符串。
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            body = node.body
            # 判断第一条语句是不是一个孤零零的字符串——那就是文档字符串。
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                # 摘掉它。如果摘完函数体就空了（这个函数只有一行文档字符串），
                # 补一个 pass 进去，否则树的结构不合法。
                node.body = body[1:] if len(body) > 1 else [ast.Pass()]
    return tree


def python_shape(src: str) -> str:
    """把一段 Python 源码变成「去掉注释后的语法树文本」。

    两个版本的结果字符串一致，就说明代码逻辑完全没变——
    哪怕空行、缩进宽度、换行位置全都不一样也没关系，
    但只要有一行代码挪了层级、写错了、多了少了，结果一定不同。
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        # 语法都不对了（文件写坏了），返回一个特殊标记，
        # 这样和任何正常版本比都会不相等，一定会报警。
        return "<SYNTAX ERROR>"
    # ast.dump 把树转成文本。不带行号（include_attributes 默认 False），
    # 所以插入注释导致的行号偏移不会影响比对结果。
    return ast.dump(_strip_docstrings(tree))


def python_tokens(src: str) -> list[str]:
    """把源码变成 token 列表（第二道检查，用来给出更具体的差异提示）。

    这一道不如语法树严格（它看不出缩进变化），但它能告诉你
    「多了 3 个 token」这种具体数字，方便定位问题在哪。
    """
    out: list[str] = []
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except Exception:
        return [ln.strip() for ln in src.splitlines() if ln.strip()]

    prev = tokenize.INDENT
    for t in toks:
        if t.type == tokenize.COMMENT:
            continue  # 丢弃 # 开头的注释
        # 文档字符串：出现在语句开头位置的孤立字符串，也算注释。
        if t.type == tokenize.STRING and prev in (
            tokenize.INDENT,
            tokenize.NEWLINE,
            tokenize.NL,
            tokenize.DEDENT,
        ):
            continue
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


# ── TypeScript：代码行比对 ──────────────────────────────────────────────────


def ts_code_lines(src: str) -> list[str]:
    """把一段 TypeScript 源码变成「去掉注释后的代码行列表」。"""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)  # 去掉 /* */ 和 {/* */} 块注释
    out: list[str] = []
    for line in src.splitlines():
        # 去掉 // 行注释。前面的 (?<!:) 是为了别把 https:// 里的双斜杠当成注释。
        line = re.sub(r"(?<!:)//.*$", "", line).strip()
        # 空行、孤立花括号不比较。
        # "{}" 也要排除：JSX 里的注释写成 {/* 说明 */}，块注释被剥掉后
        # 就剩一对空花括号，它不是代码，否则会误报「多了一行代码」。
        if line and line not in ("{", "}", "{}"):
            out.append(re.sub(r"\s+", " ", line))  # 多个空格压成一个，忽略排版差异
    return out


def _multiset_diff(old: list[str], new: list[str]) -> tuple[list[str], list[str]]:
    """比较两个列表，返回（消失的行, 多出来的行）。

    用「可重复集合」的方式比：同一行出现两次和出现一次是不同的，
    所以「把一行写了两遍」这种错误也能被抓到。
    """
    from collections import Counter

    c_old, c_new = Counter(old), Counter(new)
    removed = list((c_old - c_new).elements())  # 老的有、新的没有（或变少了）
    added = list((c_new - c_old).elements())    # 新的有、老的没有（或变多了）
    return removed, added


# ── 主流程 ──────────────────────────────────────────────────────────────────


def main() -> int:
    # 命令行给了参照点就用它，没给就和 HEAD（最近一次提交）比。
    base = sys.argv[1] if len(sys.argv) > 1 else "HEAD"
    changed = _git(["git", "diff", "--name-only", base, "--", *WATCHED]).split()

    py = [f for f in changed if f.endswith(".py")]
    ts = [f for f in changed if f.endswith((".ts", ".tsx"))]
    problems: list[str] = []

    # ---- Python：语法树比对（主检查）+ token 数量（辅助定位）----
    for f in py:
        old_src = _git(["git", "show", f"{base}:{f}"])
        new_src = open(f, encoding="utf-8").read()

        if python_shape(old_src) != python_shape(new_src):
            n_old, n_new = len(python_tokens(old_src)), len(python_tokens(new_src))
            hint = (
                f"token {n_old} -> {n_new}"
                if n_old != n_new
                else "token count same -> likely an indentation / nesting change"
            )
            problems.append(f"{f}: AST differs ({hint})")

    # ---- TypeScript：既查消失的行，也查多出来的行 ----
    for f in ts:
        old = ts_code_lines(_git(["git", "show", f"{base}:{f}"]))
        new = ts_code_lines(open(f, encoding="utf-8").read())
        removed, added = _multiset_diff(old, new)
        if removed:
            problems.append(
                f"{f}: {len(removed)} code line(s) removed, e.g. {removed[0][:70]}"
            )
        if added:
            # 只加注释的话不该出现新代码行。拆行重排也会触发，
            # 那种情况请人工确认一眼再放行。
            problems.append(
                f"{f}: {len(added)} new code line(s) appeared, e.g. {added[0][:70]}"
            )

    print(f"checked {len(py)} python + {len(ts)} ts/tsx files against {base}")
    if problems:
        for p in problems:
            print("  FAIL " + p)
        return 1
    print("OK: comments only, no code changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
