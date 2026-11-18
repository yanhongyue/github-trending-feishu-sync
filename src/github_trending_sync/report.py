"""日报文本拼装。

从「采集结果 + 当天多维表格记录」拼出当日摘要，通过飞书机器人发送。
"""

from __future__ import annotations

from typing import Iterable


def _fmt_count(n) -> str:
    """数字千分位格式化；兼容飞书读回的字符串数字；空值返回占位符。"""
    if n is None or n == "":
        return "—"
    if isinstance(n, str):
        s = n.strip().replace(",", "")
        try:
            n = int(float(s))
        except ValueError:
            return n
    return f"{n:,}"


def build_daily_report(
    *,
    snapshot_date: str,
    collected: list[dict],
    daily_records: list[dict],
    bitable_url: str,
) -> str:
    """生成日报纯文本。

    daily_records: [{record_id, fields}]，其中 fields 键为表格字段名。
    """
    total = len(collected)
    lines: list[str] = []
    lines.append(f"GitHub Trending 日报 · {snapshot_date}")
    lines.append(f"采集总数：{total} 条")

    # Top 3
    lines.append("")
    lines.append("Top 3：")
    for r in collected[:3]:
        name = r.get("repo_full_name", "?")
        today = _fmt_count(r.get("stars_today"))
        lines.append(f"  {r.get('rank')}. {name}（今日新增 ★ {today}）")

    # 进入日报的项目 + 业务备注
    lines.append("")
    lines.append("进日报项目：")
    reviewed = [r for r in daily_records if r.get("fields", {}).get("进日报") is True]
    if not reviewed:
        lines.append("  （暂无）")
    else:
        for r in reviewed:
            f = r.get("fields", {})
            name = f.get("仓库全名", "?")
            note = (f.get("业务备注") or "").strip() or "（无备注）"
            lines.append(f"  - {name}")
            lines.append(f"    业务备注：{note}")

    # 待复核数量
    pending = sum(
        1 for r in daily_records if r.get("fields", {}).get("复核状态") != "已完成"
    )
    lines.append("")
    lines.append(f"待复核：{pending} 条")

    # 多维表格链接
    link = bitable_url or "（未配置 FEISHU_BITABLE_URL，请查看多维表格）"
    lines.append(f"多维表格：{link}")

    return "\n".join(lines)


def format_report_for_log(report: str) -> str:
    return report
