"""从数据库读取实验数据并生成可视化 PNG。

用法（在 backend 目录）::

    pip install -e ".[dev]"
    python -m app.scripts.visualize_study_data

输出目录：backend/out/charts（环境变量 VIS_OUTPUT_DIR 可覆盖）
"""

from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload


def _match_gold(selected: str, gold: str, alts: list[str]) -> bool:
    return selected == gold or selected in alts


async def _fetch_formal_actions():
    from app.db.models import Action, Case, CasePresentation, Session
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        stmt = (
            select(Action)
            .join(CasePresentation, Action.case_presentation_id == CasePresentation.id)
            .join(Case, CasePresentation.case_id == Case.id)
            .join(Session, CasePresentation.session_id == Session.id)
            .options(
                selectinload(Action.presentation)
                .selectinload(CasePresentation.case),
                selectinload(Action.presentation)
                .selectinload(CasePresentation.session)
                .selectinload(Session.participant),
            )
            .where(Case.is_practice.is_(False))
        )
        rows = (await db.execute(stmt)).scalars().all()
        out: list[dict] = []
        for a in rows:
            p = a.presentation
            if p is None or p.case is None or p.session is None:
                continue
            part = p.session.participant
            cond = part.condition if part is not None else "unknown"
            out.append(
                {
                    "selected_action": a.selected_action,
                    "condition": cond,
                    "case_id": p.case_id,
                }
            )
        return out


async def _fetch_gold_match_rows():
    from app.db.models import Action, Case, CasePresentation, Session
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        stmt = (
            select(Action)
            .join(CasePresentation, Action.case_presentation_id == CasePresentation.id)
            .join(Case, CasePresentation.case_id == Case.id)
            .join(Session, CasePresentation.session_id == Session.id)
            .options(selectinload(Action.presentation).selectinload(CasePresentation.case))
            .where(Case.is_practice.is_(False))
        )
        rows = (await db.execute(stmt)).scalars().all()
        out: list[dict] = []
        for a in rows:
            p = a.presentation
            c = p.case if p else None
            if p is None or c is None:
                continue
            alts = c.gold_action_alternates or []
            out.append(
                {
                    "gold_match": _match_gold(
                        a.selected_action, c.gold_action, alts
                    ),
                }
            )
        return out


def _plot(
    rows: list[dict],
    gold_rows: list[dict],
    output_dir: Path,
) -> None:
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "SimHei", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False

    output_dir.mkdir(parents=True, exist_ok=True)

    labels_zh = {
        "send_as_is": "直接发送",
        "edit_then_send": "编辑后发送",
        "discard_and_rewrite": "弃用并重写",
        "escalate": "升级处理",
    }
    actions_order = [
        "send_as_is",
        "edit_then_send",
        "discard_and_rewrite",
        "escalate",
    ]

    if not rows:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(
            0.5,
            0.5,
            "No formal-case action rows in DB\nRun the study or submit /api/action",
            ha="center",
            va="center",
        )
        ax.set_axis_off()
        fig.savefig(
            output_dir / "01_selected_action_counts.png",
            dpi=150,
            bbox_inches="tight",
        )
        plt.close()
        fig2, ax2 = plt.subplots(figsize=(8, 4))
        ax2.text(
            0.5,
            0.5,
            "No data",
            ha="center",
            va="center",
        )
        ax2.set_axis_off()
        fig2.savefig(
            output_dir / "02_selected_by_condition.png",
            dpi=150,
            bbox_inches="tight",
        )
        plt.close()
        fig3, ax3 = plt.subplots(figsize=(5, 4))
        ax3.text(0.5, 0.5, "No data", ha="center", va="center")
        ax3.set_axis_off()
        fig3.savefig(
            output_dir / "03_gold_match_rate.png", dpi=150, bbox_inches="tight"
        )
        plt.close()
        return

    # 1) 总体
    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        counts[r["selected_action"]] += 1
    x = [labels_zh.get(a, a) for a in actions_order]
    y = [counts.get(a, 0) for a in actions_order]
    fig, ax = plt.subplots(figsize=(9, 4))
    colors = ["#3b82f6", "#8b5cf6", "#f59e0b", "#ef4444"]
    bars = ax.bar(x, y, color=colors)
    ax.set_ylabel("Count")
    ax.set_title("Formal cases: distribution of selected action")
    for b, v in zip(bars, y):
        ax.text(
            b.get_x() + b.get_width() / 2,
            b.get_height(),
            str(v),
            ha="center",
            va="bottom",
        )
    plt.xticks(rotation=15, ha="right")
    fig.tight_layout()
    fig.savefig(
        output_dir / "01_selected_action_counts.png", dpi=150, bbox_inches="tight"
    )
    plt.close()

    # 2) 按条件
    by_cond: dict[str, dict[str, int]] = {
        "plain": defaultdict(int),
        "guardrail": defaultdict(int),
    }
    for r in rows:
        cond = r.get("condition") or "plain"
        if cond in by_cond:
            by_cond[cond][r["selected_action"]] += 1

    fig, ax = plt.subplots(figsize=(10, 5))
    x_pos = range(len(actions_order))
    width = 0.35
    plain_vals = [by_cond["plain"].get(a, 0) for a in actions_order]
    guard_vals = [by_cond["guardrail"].get(a, 0) for a in actions_order]
    ax.bar(
        [i - width / 2 for i in x_pos],
        plain_vals,
        width,
        label="plain",
        color="#64748b",
    )
    ax.bar(
        [i + width / 2 for i in x_pos],
        guard_vals,
        width,
        label="guardrail",
        color="#0ea5e9",
    )
    ax.set_xticks(list(x_pos))
    ax.set_xticklabels(
        [labels_zh.get(a, a) for a in actions_order], rotation=15, ha="right"
    )
    ax.set_ylabel("Count")
    ax.set_title("Selected action by UI condition (plain / guardrail)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(
        output_dir / "02_selected_by_condition.png", dpi=150, bbox_inches="tight"
    )
    plt.close()

    # 3) 金标准
    if gold_rows:
        hit = sum(1 for r in gold_rows if r["gold_match"])
        miss = len(gold_rows) - hit
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.pie(
            [hit, miss],
            labels=[f"gold match ({hit})", f"no match ({miss})"],
            autopct="%1.1f%%",
            colors=["#22c55e", "#fecaca"],
        )
        ax.set_title("Formal cases: gold / alternates match rate")
        fig.tight_layout()
        fig.savefig(
            output_dir / "03_gold_match_rate.png", dpi=150, bbox_inches="tight"
        )
        plt.close()


async def main() -> None:
    out_dir = Path(
        os.environ.get(
            "VIS_OUTPUT_DIR",
            Path(__file__).resolve().parents[2] / "out" / "charts",
        )
    )
    try:
        import matplotlib.pyplot as plt  # noqa: F401
    except ImportError as e:
        raise SystemExit(
            "Install: pip install matplotlib  or  pip install -e \".[dev]\""
        ) from e

    rows = await _fetch_formal_actions()
    gold_rows = await _fetch_gold_match_rows()
    _plot(rows, gold_rows, out_dir)
    print(f"Charts written to: {out_dir.resolve()}")
    for p in sorted(out_dir.glob("*.png")):
        print(f"  - {p.name}")


if __name__ == "__main__":
    asyncio.run(main())
