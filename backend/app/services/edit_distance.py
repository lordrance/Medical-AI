from __future__ import annotations


def levenshtein(a: str, b: str) -> int:
    """Character-level Levenshtein edit distance, O(n*m) time, O(min(n,m)) space."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) < len(b):
        a, b = b, a

    n, m = len(a), len(b)
    prev = list(range(m + 1))
    curr = [0] * (m + 1)

    for i in range(1, n + 1):
        curr[0] = i
        ca = a[i - 1]
        for j in range(1, m + 1):
            cost = 0 if ca == b[j - 1] else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev, curr = curr, prev
    return prev[m]
