# RUNBOOK.md — 运行手册

## 1. 前置检查清单

每次运行前确认：

- [ ] `.env` 已创建，必填项齐全（`FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_BITABLE_APP_TOKEN`、`FEISHU_BITABLE_TABLE_ID`、`FEISHU_CHAT_ID`）
- [ ] `playwright install chromium` 已执行
- [ ] 网络可访问 `github.com` 与 `open.feishu.cn`
- [ ] 应用已被添加为多维表格协作者，机器人已入测试群

快速自检命令：

```bash
python -m github_trending_sync collect
```

能打印出 Top 10 即说明采集链路正常。

## 2. 运行

```bash
# 完整流程（采集 + 写库 + 发日报）
python -m github_trending_sync sync

# 仅采集验证
python -m github_trending_sync collect

# 仅发日报（人工复核后补发）
python -m github_trending_sync report
```

退出码：`0` 成功，`1` 失败。

## 3. 检查运行结果

1. **日志**：stdout 输出每一步状态；`sync` 末尾会打印日报全文。
2. **多维表格**：打开 `FEISHU_BITABLE_URL`，确认当天有 10 条记录、字段值正确、人工字段未被改动。
3. **测试群**：确认机器人消息已送达。
4. **证据留存**：可将日志重定向保存：

```bash
python -m github_trending_sync sync > evidence/run-$(date +%F-%H%M%S).log 2>&1
```

## 4. 停止

任务为一次性进程，非长驻服务：

- 前台运行：`Ctrl+C` 中断。
- 若用 cron 触发：删除对应 crontab 条目即可停止调度。
- 无需额外清理（进程退出即结束，不残留后台线程）。

## 5. 重跑（同日）

直接再次执行 `python -m github_trending_sync sync` 即可：

- 系统字段按最新采集结果更新；
- 不会产生重复记录；
- 人工四字段保持不变。

## 6. 定时调度（可选）

使用 cron 每天定时执行（示例为每天 09:00，`Asia/Shanghai`）：

```cron
0 9 * * * cd /path/to/github-trending-feishu-sync && PYTHONPATH=src /usr/bin/python3 -m github_trending_sync sync >> evidence/cron.log 2>&1
```

## 7. 常见故障与处理

| 现象 | 处理 |
|---|---|
| `缺少飞书相关配置：...` | 复制 `config.example.env` 为 `.env` 并填写缺失项 |
| `无法访问 GitHub Trending 页面` | 确认网络可达 github.com；受限内网证书异常设 `IGNORE_HTTPS_ERRORS=true` |
| `页面已打开但未发现任何仓库卡片` | 空榜或页面改版；稍后重试，若持续失败更新 `scraper.py` 选择器 |
| `飞书鉴权失败 code=99991xxx` | 核对 App ID/Secret；确认应用已开通 bitable/im 权限 |
| `飞书接口错误 code=...` | 按错误码核对字段类型；确认应用是表格协作者、机器人已入群 |
| `飞书接口限流/暂不可用` | 已自动重试；持续失败则降低频率或稍后重跑 |
| 群未收到消息 | 确认机器人已入群、`FEISHU_CHAT_ID` 正确、`im:message` 权限已开 |
| 表格出现重复记录 | 检查「快照日期」是否一致；确认未手工复制行（唯一键逻辑不覆盖手工新增） |

## 8. 凭证安全

- `.env` 已在 `.gitignore` 中，切勿 `git add`。
- 提交前确认仓库中无 `App Secret`、token、手机号、真实姓名等敏感信息。
- 日志中不打印 `App Secret`；如需留存日志，请复核后再提交脱敏版本。
