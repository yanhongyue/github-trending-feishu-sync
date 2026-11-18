"""任务入口。

用法：
    python -m github_trending_sync [sync|collect|report]

- sync    ：采集 -> 幂等写入多维表格 -> 发送当日日报（默认）
- collect ：仅采集并打印结果（不访问飞书，用于本地验证采集链路）
- report  ：不采集，仅按当天表格记录发送日报（用于人工复核后补发）
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from . import __version__
from .config import Config
from .errors import SyncError
from .feishu import FeishuClient
from .normalize import now_timestamp_ms, parse_count, snapshot_date, snapshot_date_timestamp_ms
from .report import build_daily_report
from .scraper import scrape_trending

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("sync")

# 系统字段：采集写入/重跑更新；人工字段绝不触碰
_UPDATE_FIELDS = ("排名", "项目简介", "主语言", "总Star数", "Fork数", "周期新增Star", "采集时间")


def _build_fields(repo: dict, snapshot_ms: int, collected_ms: int) -> dict:
    fields = {
        "快照日期": snapshot_ms,
        "排名": repo["rank"],
        "仓库全名": repo["repo_full_name"],
        "仓库链接": {"link": repo["repo_url"], "text": repo["repo_full_name"]},
        "项目简介": repo["description"],
        "主语言": repo["language"],
        "采集时间": collected_ms,
    }
    if repo.get("stars") is not None:
        fields["总Star数"] = repo["stars"]
    if repo.get("forks") is not None:
        fields["Fork数"] = repo["forks"]
    if repo.get("stars_today") is not None:
        fields["周期新增Star"] = repo["stars_today"]
    return fields


def _pick_update_fields(fields: dict) -> dict:
    return {k: fields[k] for k in _UPDATE_FIELDS if k in fields}


def _daily_records(records: list[dict], snapshot_ms: int, tz: str) -> list[dict]:
    """过滤出当天记录，并返回 {仓库全名: record} 映射。

    日期字段读取值为毫秒时间戳，按配置时区转回日期字符串后比较，规避时区口径差异。
    """
    daily: list[dict] = []
    for rec in records:
        ts = rec.get("fields", {}).get("快照日期")
        if ts is None:
            continue
        try:
            d = datetime.fromtimestamp(int(ts) / 1000, tz=ZoneInfo(tz)).strftime("%Y-%m-%d")
        except Exception:
            continue
        if d == snapshot_date(tz):
            daily.append(rec)
    return daily


def do_collect(cfg: Config) -> list[dict]:
    log.info("开始采集：%s（Top %d）", cfg.trending_url, cfg.top_n)
    repos = scrape_trending(
        cfg.trending_url,
        cfg.top_n,
        ignore_https_errors=cfg.ignore_https_errors,
        timeout_ms=cfg.page_timeout_ms,
    )
    log.info("采集完成，共 %d 条", len(repos))
    for r in repos:
        log.info(
            "#%s %s | ★%s fork=%s today=%s | %s",
            r["rank"], r["repo_full_name"],
            r["stars"], r["forks"], r["stars_today"], r["language"],
        )
    return repos


def do_sync(cfg: Config) -> int:
    cfg.validate_for_write()
    repos = do_collect(cfg)

    client = FeishuClient(
        app_id=cfg.feishu_app_id,
        app_secret=cfg.feishu_app_secret,
        base_url=cfg.feishu_base_url,
        http_timeout=cfg.http_timeout,
        max_retries=cfg.max_retries,
        retry_backoff=cfg.retry_backoff,
        ca_bundle=cfg.feishu_ca_bundle,
    )

    tz = cfg.timezone
    snapshot = snapshot_date(tz)
    snapshot_ms = snapshot_date_timestamp_ms(tz)
    collected_ms = now_timestamp_ms(tz)

    log.info("读取多维表格现有记录…")
    records = client.list_records(cfg.bitable_app_token, cfg.bitable_table_id)
    daily = _daily_records(records, snapshot_ms, tz)
    existing = {r.get("fields", {}).get("仓库全名"): r for r in daily}

    created = updated = 0
    for repo in repos:
        fields = _build_fields(repo, snapshot_ms, collected_ms)
        name = repo["repo_full_name"]
        if name in existing:
            upd = _pick_update_fields(fields)
            client.update_record(
                cfg.bitable_app_token, cfg.bitable_table_id,
                existing[name]["record_id"], upd,
            )
            updated += 1
            log.info("更新记录：%s（排名 %s）", name, repo["rank"])
        else:
            client.create_record(
                cfg.bitable_app_token, cfg.bitable_table_id, fields
            )
            created += 1
            log.info("新建记录：%s（排名 %s）", name, repo["rank"])

    log.info("写入完成：新建 %d 条，更新 %d 条", created, updated)

    # 重新读取当天记录（含人工字段），用于日报
    records = client.list_records(cfg.bitable_app_token, cfg.bitable_table_id)
    daily = _daily_records(records, snapshot_ms, tz)
    report = build_daily_report(
        snapshot_date=snapshot,
        collected=repos,
        daily_records=daily,
        bitable_url=cfg.bitable_url,
    )
    client.send_text(cfg.chat_id, report)
    log.info("日报已发送到测试群")

    print("\n" + "=" * 40)
    print(report)
    print("=" * 40)
    return 0


def do_report(cfg: Config) -> int:
    cfg.validate_for_write()
    client = FeishuClient(
        app_id=cfg.feishu_app_id,
        app_secret=cfg.feishu_app_secret,
        base_url=cfg.feishu_base_url,
        http_timeout=cfg.http_timeout,
        max_retries=cfg.max_retries,
        retry_backoff=cfg.retry_backoff,
        ca_bundle=cfg.feishu_ca_bundle,
    )
    tz = cfg.timezone
    snapshot_ms = snapshot_date_timestamp_ms(tz)
    records = client.list_records(cfg.bitable_app_token, cfg.bitable_table_id)
    daily = _daily_records(records, snapshot_ms, tz)
    report = build_daily_report(
        snapshot_date=snapshot_date(tz),
        collected=_collect_from_records(daily),
        daily_records=daily,
        bitable_url=cfg.bitable_url,
    )
    client.send_text(cfg.chat_id, report)
    log.info("日报已发送到测试群")
    print("\n" + "=" * 40)
    print(report)
    print("=" * 40)
    return 0


def _collect_from_records(daily: list[dict]) -> list[dict]:
    """从当天记录还原 Top N 排序列表，供 report 子命令使用。

    飞书数字字段读回为字符串，此处转回数字以便排序与展示。
    """
    repos = []
    for rec in daily:
        f = rec.get("fields", {})
        if f.get("仓库全名") is None:
            continue
        repos.append({
            "rank": parse_count(f.get("排名")),
            "repo_full_name": f.get("仓库全名"),
            "stars_today": parse_count(f.get("周期新增Star")),
        })
    repos.sort(key=lambda x: (x["rank"] is None, x["rank"] or 0))
    return repos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="github_trending_sync")
    parser.add_argument("command", nargs="?", default="sync",
                        choices=["sync", "collect", "report"])
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)

    try:
        cfg = Config.from_env()
    except SyncError as exc:
        log.error("配置错误：%s", exc.message)
        if exc.hint:
            log.error("排查方向：%s", exc.hint)
        return 1

    try:
        if args.command == "collect":
            do_collect(cfg)
        elif args.command == "report":
            return do_report(cfg)
        else:
            return do_sync(cfg)
    except SyncError as exc:
        log.error("任务失败：%s", exc.message)
        if exc.hint:
            log.error("排查方向：%s", exc.hint)
        return 1
    except Exception as exc:  # 兜底，避免静默成功
        log.exception("未预期错误：%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
