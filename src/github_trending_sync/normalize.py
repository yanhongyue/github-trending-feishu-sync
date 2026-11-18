"""采集字段标准化。

将 GitHub Trending 页面上的展示文本转换为多维表格可写入的结构化值：
- "1.2k" / "2,345" -> 数字
- 缺失主语言 -> "未标注"
- 缺失数字 -> None（不填 0）
- 相对链接 -> 绝对链接
"""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo


def parse_count(text: str | None) -> int | None:
    """解析计数文本，返回整数；无法解析或为空返回 None。

    支持：9,525 / 1.2k / 1,376 / "1,005 stars today" 等。
    """
    if not text:
        return None
    t = text.strip().lower().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*([kmb]?)", t)
    if not m:
        return None
    num = float(m.group(1))
    suffix = m.group(2)
    if suffix == "k":
        num *= 1_000
    elif suffix == "m":
        num *= 1_000_000
    elif suffix == "b":
        num *= 1_000_000_000
    return int(round(num))


def normalize_language(text: str | None) -> str:
    """主语言标准化，缺失时返回“未标注”。"""
    t = (text or "").strip()
    return t if t else "未标注"


def normalize_description(text: str | None) -> str:
    """项目简介：缺失时保持空字符串（不填占位符）。"""
    return (text or "").strip()


def absolute_url(href: str | None, base: str = "https://github.com") -> str:
    """将相对链接转为绝对地址。"""
    h = (href or "").strip()
    if h.startswith("http://") or h.startswith("https://"):
        return h
    return base.rstrip("/") + "/" + h.lstrip("/")


def now_timestamp_ms(tz_name: str = "Asia/Shanghai") -> int:
    """当前时间的毫秒时间戳（用于日期时间字段）。"""
    return int(datetime.now(ZoneInfo(tz_name)).timestamp() * 1000)


def snapshot_date(tz_name: str = "Asia/Shanghai") -> str:
    """快照日期字符串，YYYY-MM-DD（Asia/Shanghai）。"""
    return datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d")


def snapshot_date_timestamp_ms(tz_name: str = "Asia/Shanghai") -> int:
    """快照日期当天 00:00 的毫秒时间戳（用于飞书“日期”字段）。"""
    d = datetime.now(ZoneInfo(tz_name)).date()
    dt = datetime(d.year, d.month, d.day, tzinfo=ZoneInfo(tz_name))
    return int(dt.timestamp() * 1000)
