"""多维表格初始化脚本（可选工具）。

创建多维表格并建立 14 个标准字段，供面试官/候选人一键建表。
复用默认表的「文本」主字段为「仓库全名」、「日期」字段为「快照日期」，
删除默认「附件」「单选」冗余字段，其余字段按题面创建。

用法：
    # 新建表并建字段
    PYTHONPATH=src python3 scripts/setup_bitable.py --name "GitHub Trending 日报"
    # 在已有表上补齐字段（幂等）
    PYTHONPATH=src python3 scripts/setup_bitable.py --app-token <t> --table-id <id>

成功后打印 app_token / table_id / url，将其回填 .env 即可。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from github_trending_sync.config import Config  # noqa: E402
from github_trending_sync.feishu import FeishuClient  # noqa: E402

# 14 个字段定义（字段名, 类型码, property）
# type: 1 多行文本 2 数字 3 单选 5 日期 7 复选框 15 超链接
FIELDS = [
    ("快照日期", 5, {"date_formatter": "yyyy/MM/dd"}),
    ("排名", 2, {}),
    ("仓库全名", 1, {}),
    ("仓库链接", 15, {}),
    ("项目简介", 1, {}),
    ("主语言", 1, {}),
    ("总Star数", 2, {}),
    ("Fork数", 2, {}),
    ("周期新增Star", 2, {}),
    ("采集时间", 5, {"date_formatter": "yyyy/MM/dd HH:mm"}),
    ("复核状态", 3, {"options": [{"name": "待复核"}, {"name": "已完成"}]}),
    ("业务判断", 3, {"options": [{"name": "未判断"}, {"name": "跟进"},
                                 {"name": "观察"}, {"name": "忽略"}]}),
    ("业务备注", 1, {}),
    ("进日报", 7, {}),
]

# 默认表复用/删除的字段名
RENAME_MAP = {"文本": "仓库全名", "日期": "快照日期"}
DROP_FIELDS = {"附件", "单选"}


def _list_fields(c, app_token, table_id):
    items, page_token = [], None
    while True:
        params = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
        r = c._request(
            "GET",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
            params=params,
        )
        d = r["data"]
        items.extend(d.get("items", []))
        if d.get("has_more"):
            page_token = d.get("page_token")
        else:
            break
    return items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="GitHub Trending 日报")
    ap.add_argument("--app-token", default="")
    ap.add_argument("--table-id", default="")
    args = ap.parse_args()

    cfg = Config.from_env()
    if not cfg.feishu_app_id or not cfg.feishu_app_secret:
        print("缺少 FEISHU_APP_ID / FEISHU_APP_SECRET，请先完成飞书授权并配置 .env。",
              file=sys.stderr)
        return 1
    c = FeishuClient(
        app_id=cfg.feishu_app_id, app_secret=cfg.feishu_app_secret,
        base_url=cfg.feishu_base_url, ca_bundle=cfg.feishu_ca_bundle,
        http_timeout=cfg.http_timeout, max_retries=cfg.max_retries,
        retry_backoff=cfg.retry_backoff,
    )

    # 1) 新建或复用表
    if args.app_token and args.table_id:
        app_token, table_id, url = args.app_token, args.table_id, ""
        print(f"[1/4] 复用已有表 app_token={app_token} table_id={table_id}")
    else:
        r = c._request("POST", "/open-apis/bitable/v1/apps", json_body={"name": args.name})
        app_token = r["data"]["app"]["app_token"]
        table_id = r["data"]["app"]["default_table_id"]
        url = r["data"]["app"]["url"]
        print(f"[1/4] 已创建多维表格 app_token={app_token} table_id={table_id}")

    # 2) 复用默认字段（重命名）与删除冗余字段
    fields = _list_fields(c, app_token, table_id)
    for f in fields:
        fname = f["field_name"]
        if fname in RENAME_MAP:
            target = RENAME_MAP[fname]
            # 目标名已存在则跳过（避免重复）
            if any(x["field_name"] == target for x in fields):
                continue
            c._request(
                "PUT",
                f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields/{f['field_id']}",
                json_body={"field_name": target, "type": f["type"]},
            )
            print(f"      复用字段 {fname} -> {target}")
        elif fname in DROP_FIELDS:
            c._request(
                "DELETE",
                f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields/{f['field_id']}",
            )
            print(f"      删除冗余字段 {fname}")
    print("[2/4] 默认字段处理完成")

    # 3) 创建缺失字段
    existing = {f["field_name"] for f in _list_fields(c, app_token, table_id)}
    for name, ftype, prop in FIELDS:
        if name in existing:
            continue
        body = {"field_name": name, "type": ftype}
        if prop:
            body["property"] = prop
        c._request(
            "POST",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
            json_body=body,
        )
        print(f"      创建字段 {name} (type={ftype})")
    print("[3/4] 字段创建完成")

    # 3.5) 清理飞书新建表格默认自带的空记录（fields 为空的行）
    recs = []
    page_token = None
    while True:
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        r = c._request(
            "GET",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            params=params,
        )
        d = r["data"]
        recs.extend(d.get("items", []))
        if d.get("has_more"):
            page_token = d.get("page_token")
        else:
            break
    empty_ids = [x["record_id"] for x in recs if not x.get("fields")]
    if empty_ids:
        c._request(
            "POST",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_delete",
            json_body={"records": empty_ids},
        )
        print(f"[3.5/4] 清理默认空记录 {len(empty_ids)} 条")

    # 4) 输出结果
    final_fields = _list_fields(c, app_token, table_id)
    print(f"\n[4/4] 共 {len(final_fields)} 个字段：")
    print("  " + ", ".join(f["field_name"] for f in final_fields))
    print("\n请将以下值回填 .env：")
    print(f"  FEISHU_BITABLE_APP_TOKEN={app_token}")
    print(f"  FEISHU_BITABLE_TABLE_ID={table_id}")
    if url:
        print(f"  FEISHU_BITABLE_URL={url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
