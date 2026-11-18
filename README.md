# GitHub Trending 每日同步与飞书日报

使用**真实浏览器（headless Chromium）**采集 [GitHub Trending 日榜](https://github.com/trending?since=daily) 当日 Top 10，标准化后通过**飞书开放平台 API** 写入多维表格，并向测试群发送当日摘要。

核心特性：

- 数据仅来源于 GitHub Trending 页面当次展示结果，不使用替代数据源
- 幂等写入：业务唯一键 = `快照日期 + 仓库全名`，同日重跑只更新、不重复
- 重跑绝不覆盖人工字段（复核状态 / 业务判断 / 业务备注 / 进日报）
- 凭证零硬编码，面试官替换 `.env` 即可运行，无需改源码
- 错误场景输出明确原因与排查方向，非零退出码，不静默成功、不泄漏凭证

---

## 1. 环境与安装

| 依赖 | 要求 |
|---|---|
| Python | 3.9+（开发验证于 3.11） |
| 系统 | Linux / macOS / Windows 均可 |
| 网络 | 可访问 github.com 与 open.feishu.cn |

```bash
# 1) 安装 Python 依赖
pip install -r requirements.txt

# 2) 安装 Chromium（真实浏览器内核）
playwright install chromium
```

> 若已用 `make`，可执行 `make install` 一步完成以上两步。

---

## 2. 飞书侧准备（一次性）

本方案使用**测试企业/测试租户 + 测试版本自建应用**，全部资源由运行者自行创建，不依赖任何私有 ID。

### 2.1 创建自建应用并开通权限

1. 登录 [飞书开放平台](https://open.feishu.cn/)，进入「开发者后台」。
2. 创建**企业自建应用**（测试企业即可，无需发布生产版本）。
3. 在「权限管理」中开通：
   - `bitable:app`（多维表格读写）
   - `im:message`（机器人发送群消息）
   - （消息发送通常还需 `im:message:send_as_bot`，按后台提示勾选即可）
4. 在「凭证与基础信息」页获取 **App ID** 与 **App Secret**。

### 2.2 创建多维表格

1. 新建一个多维表格，按下方「字段定义」建好 14 个字段（字段名与类型必须一致）。
2. 将**应用添加为多维表格协作者**（右上角「…」→ 添加协作者 → 选择该应用），否则 API 无权限读写。
3. 获取两个标识：
   - `App Token`：多维表格 URL 中 `base/` 后的一段，形如 `bascnxxxxxxxx`
   - `Table ID`：数据表 URL 中 `table=` 后的一段，形如 `tblxxxxxxxx`

### 2.3 创建测试群并拉入机器人

1. 新建测试群，将应用的**机器人**加入群（应用「添加应用能力」→ 启用机器人）。
2. 获取 `chat_id`：群设置中「群信息」→ 群 ID，或通过[获取群列表 API](https://open.feishu.cn/document/server-docs/im-v1/chat/list) 查询。

### 2.4 自动化建表（可选）

建好应用并开通权限后，可用脚本一键创建多维表格和 14 个字段：

```bash
PYTHONPATH=src python3 scripts/setup_bitable.py --name "GitHub Trending 日报"
```

脚本会输出 `FEISHU_BITABLE_APP_TOKEN` / `FEISHU_BITABLE_TABLE_ID` / `FEISHU_BITABLE_URL`，回填 `.env` 即可。脚本同时会清理飞书新建表格默认自带的空记录。

---

## 3. 配置

```bash
cp config.example.env .env
# 编辑 .env，填入你的测试凭证与资源标识
```

全部配置项：

| 配置项 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `GITHUB_TRENDING_URL` | 否 | `https://github.com/trending?since=daily` | 采集地址，不要改成其它榜单 |
| `TOP_N` | 否 | `10` | 采集条数 |
| `TZ_NAME` | 否 | `Asia/Shanghai` | 快照日期与采集时间时区 |
| `IGNORE_HTTPS_ERRORS` | 否 | `false` | 仅受限内网存在 TLS 证书异常时设 `true` |
| `PAGE_TIMEOUT_MS` | 否 | `60000` | 页面加载超时（毫秒） |
| `FEISHU_BASE_URL` | 否 | `https://open.feishu.cn` | 开放平台网关 |
| `FEISHU_APP_ID` | 是 | 空 | 自建应用 App ID |
| `FEISHU_APP_SECRET` | 是 | 空 | 自建应用 App Secret |
| `FEISHU_CA_BUNDLE` | 否 | 空 | 自定义 CA 证书文件路径（受限内网代理时使用） |
| `FEISHU_BITABLE_APP_TOKEN` | 是 | 空 | 多维表格 App Token |
| `FEISHU_BITABLE_TABLE_ID` | 是 | 空 | 数据表 ID |
| `FEISHU_BITABLE_URL` | 否 | 空 | 表格网页链接（用于日报展示） |
| `FEISHU_CHAT_ID` | 是 | 空 | 测试群 chat_id |
| `HTTP_TIMEOUT` | 否 | `20` | 飞书请求超时（秒） |
| `MAX_RETRIES` | 否 | `3` | 限流/网络错误重试次数 |
| `RETRY_BACKOFF` | 否 | `1.5` | 重试退避基数（秒） |

> 凭证与资源标识只从环境变量/`.env` 读取，源码中零硬编码。

---

## 4. 多维表格字段定义

| 字段 | 类型 | 说明 | 写入方 |
|---|---|---|---|
| 快照日期 | 日期 | 采集当天 | 系统 |
| 排名 | 数字 | 页面展示顺序 | 系统 |
| 仓库全名 | 文本 | `owner/repo` | 系统 |
| 仓库链接 | 超链接 | GitHub URL | 系统 |
| 项目简介 | 多行文本 | 页面描述 | 系统 |
| 主语言 | 文本 | 缺失时为「未标注」 | 系统 |
| 总Star数 | 数字 | 总 Star | 系统 |
| Fork数 | 数字 | Fork | 系统 |
| 周期新增Star | 数字 | 当日新增 Star | 系统 |
| 采集时间 | 日期时间 | 实际采集时间 | 系统 |
| 复核状态 | 单选 | `待复核` / `已完成` | **人工** |
| 业务判断 | 单选 | `未判断` / `跟进` / `观察` / `忽略` | **人工** |
| 业务备注 | 多行文本 | 业务价值、场景或忽略原因 | **人工** |
| 进日报 | 复选框 | 是否进入当日摘要 | **人工** |

> 加粗「人工」的四列由业务人员填写，程序**永不写入、永不覆盖**。

---

## 5. 运行

```bash
# 一键运行：采集 → 幂等写入 → 发送日报
python -m github_trending_sync sync

# 仅采集（不访问飞书，用于验证采集链路）
python -m github_trending_sync collect

# 仅发送日报（人工复核勾选「进日报」后补发）
python -m github_trending_sync report
```

等价地可用 `make sync` / `make collect` / `make report`。

**典型工作流**：

```bash
python -m github_trending_sync sync   # 采集落库 + 首次日报
# → 业务人员在表格中复核、勾选「进日报」
python -m github_trending_sync report # 按最新勾选状态补发日报
```

### 退出码

| 退出码 | 含义 |
|---|---|
| `0` | 成功 |
| `1` | 失败（配置缺失 / 采集失败 / 飞书错误等），日志已输出原因与排查方向 |

### 幂等与人工字段保护

- 唯一键 = `快照日期 + 仓库全名`。
- 重跑时命中已有记录则**仅更新**：排名、项目简介、主语言、总Star数、Fork数、周期新增Star、采集时间。
- `复核状态 / 业务判断 / 业务备注 / 进日报` 四个字段不出现在任何写库请求中，从机制上保证不被覆盖。

---

## 6. 容错与响应说明

| 场景 | 表现 |
|---|---|
| 配置或凭证缺失 | 启动即报错，列出缺失项，退出码 1 |
| 飞书鉴权失败 | 报出飞书错误码与权限排查方向，退出码 1 |
| 字段缺失/类型错误 | 报出对应字段与接口错误码，退出码 1 |
| 页面不可访问 | 报网络/证书排查方向，退出码 1 |
| 页面无记录 | 报「未发现仓库卡片」，退出码 1 |
| 飞书超时/限流(429等) | 指数退避自动重试，超阈值后报错退出 1 |
| 同日重复运行 | 走更新分支，不产生重复记录 |

失败信息不会打印 `App Secret` 等凭证。日志仅输出 `App ID` 之外的必要上下文。

---

## 7. 目录结构

```text
github-trending-feishu-sync/
├── src/github_trending_sync/
│   ├── __main__.py        # 入口与编排（sync/collect/report）
│   ├── scraper.py         # Playwright 采集与解析
│   ├── normalize.py       # 数字/日期/缺失值标准化
│   ├── feishu.py          # 飞书 API 客户端（鉴权+表格+消息）
│   ├── report.py          # 日报拼装
│   ├── config.py          # 配置加载
│   └── errors.py          # 异常体系
├── config.example.env     # 脱敏配置示例
├── requirements.txt
├── Makefile
├── scripts/
│   └── setup_bitable.py   # 一键建表 + 建 14 字段
├── README.md / SOLUTION.md / RUNBOOK.md
└── evidence/              # 运行证据（脱敏）
```

---

## 8. 常见问题排查

| 现象 | 原因与处理 |
|---|---|
| `无法访问 GitHub Trending 页面` | 网络不可达 github.com；确认能直连，或配置代理；内网证书异常时设 `IGNORE_HTTPS_ERRORS=true` |
| `未发现任何仓库卡片` | 页面结构变化或空榜；确认浏览器版本，稍后重试 |
| `飞书鉴权失败 code=99991xxx` | App ID/Secret 错误，或应用未开通 bitable/im 权限 |
| `飞书接口错误 code=...` | 按错误码核对字段类型；确认应用已被添加为表格协作者、机器人已入群 |
| `缺少飞书相关配置` | 未复制 `.env` 或未填写必填项 |

更多运行与故障细节见 [RUNBOOK.md](./RUNBOOK.md)。
