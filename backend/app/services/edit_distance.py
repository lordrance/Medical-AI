"""★ 编辑距离 —— 衡量「医生把 AI 草稿改了多少」的核心指标。

这是本研究最重要的连续型因变量之一：
  0    = 一个字都没改（完全照搬 AI）
  很小 = 只动了标点或个别词（走过场式的修改）
  很大 = 大幅重写（不信任 AI）

配合「有没有埋错」一起看，就能区分「该改的改了」和「瞎改一通」。
"""

from __future__ import annotations


def levenshtein(a: str, b: str) -> int:
    """Character-level Levenshtein edit distance, O(n*m) time, O(min(n,m)) space.

    中文：算两段文本的「莱文斯坦距离」——把 a 变成 b 最少需要多少次
    单字符操作（增、删、改）。中文按字算，一个汉字算一个字符。

    例：「你好吗」→「你好呀」= 1（改了一个字）
    """
    # 三个快速返回，避免走完整算法：
    if a == b:
        return 0            # 完全相同
    if not a:
        return len(b)       # 一边是空的 → 距离就是另一边的长度
    if not b:
        return len(a)
    # 保证 a 是较长的那个，这样下面的滚动数组只有 min(n,m)+1 大，更省内存
    if len(a) < len(b):
        a, b = b, a

    n, m = len(a), len(b)
    # ★ 标准动态规划，但只保留两行而不是整个 n×m 矩阵（「滚动数组」优化）。
    # prev = 上一行的结果，curr = 正在算的这一行。
    # 医生的回复可能上千字，完整矩阵会占几 MB，滚动数组只占几 KB。
    prev = list(range(m + 1))  # 第 0 行：把空串变成 b 的前 j 个字符，需要 j 步
    curr = [0] * (m + 1)

    for i in range(1, n + 1):
        curr[0] = i          # 把 a 的前 i 个字符变成空串，需要 i 步
        ca = a[i - 1]
        for j in range(1, m + 1):
            # 这两个字符一样就不花代价，不一样就算一次「替换」
            cost = 0 if ca == b[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,          # 删除 a 的这个字符
                curr[j - 1] + 1,      # 插入 b 的这个字符
                prev[j - 1] + cost,   # 替换（或字符相同，免费）
            )
        # 交换两行：这一行算完了，下一轮它就是「上一行」。
        # 用交换而不是新建列表，避免每轮都分配内存。
        prev, curr = curr, prev
    return prev[m]
