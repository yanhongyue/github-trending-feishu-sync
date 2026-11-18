"""配置加载。

所有凭证与外部资源标识均从环境变量读取，绝不硬编码。
优先读取进程环境变量；若存在 `.env` 文件则补足缺失项（.env 不覆盖已存在变量）。

依赖：python-dotenv（可选，未安装时仅使用环境变量）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ConfigError

# 项目根目录（用于定位 .env）
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv_if_available() -> None:
    """尽力加载 .env；dotenv 缺失时不报错，直接使用真实环境变量。"""
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(PROJECT_ROOT / ".env")
    except Exception:
        pass


@dataclass
class Config:
    # GitHub
    trending_url: str = "https://github.com/trending?since=daily"
    top_n: int = 10
    timezone: str = "Asia/Shanghai"
    # 沙箱/内网代理等特殊环境下的 TLS 证书异常兜底，默认关闭
    ignore_https_errors: bool = False

    # 飞书开放平台
    feishu_base_url: str = "https://open.feishu.cn"
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    # 可选：自定义 CA 证书文件路径（受限内网代理场景）；留空用默认验证
    feishu_ca_bundle: str = ""
    bitable_app_token: str = ""
    bitable_table_id: str = ""
    # 多维表格网页版链接（用于日报中展示），可选
    bitable_url: str = ""
    chat_id: str = ""

    # 重试与超时
    http_timeout: float = 20.0
    max_retries: int = 3
    retry_backoff: float = 1.5

    # 页面加载超时
    page_timeout_ms: int = 60_000

    # 人工字段（重跑时绝不覆盖）
    manual_fields: tuple[str, ...] = field(
        default=("复核状态", "业务判断", "业务备注", "进日报"),
    )

    @classmethod
    def from_env(cls) -> "Config":
        _load_dotenv_if_available()

        def get_int(name: str, default: int) -> int:
            raw = os.getenv(name, "").strip()
            if not raw:
                return default
            try:
                return int(raw)
            except ValueError as exc:
                raise ConfigError(
                    f"配置项 {name} 必须是整数，当前值：{raw!r}",
                    f"请检查 .env 中 {name} 的取值。",
                ) from exc

        def get_bool(name: str, default: bool) -> bool:
            raw = os.getenv(name, "").strip().lower()
            if not raw:
                return default
            if raw in ("1", "true", "yes", "on"):
                return True
            if raw in ("0", "false", "no", "off"):
                return False
            raise ConfigError(
                f"配置项 {name} 必须是布尔值，当前值：{raw!r}",
                f"请使用 true/false。",
            )

        cfg = cls(
            trending_url=os.getenv("GITHUB_TRENDING_URL", cls.trending_url).strip(),
            top_n=get_int("TOP_N", 10),
            timezone=os.getenv("TZ_NAME", "Asia/Shanghai").strip(),
            ignore_https_errors=get_bool("IGNORE_HTTPS_ERRORS", False),
            feishu_base_url=os.getenv("FEISHU_BASE_URL", cls.feishu_base_url).strip().rstrip("/"),
            feishu_app_id=os.getenv("FEISHU_APP_ID", "").strip(),
            feishu_app_secret=os.getenv("FEISHU_APP_SECRET", "").strip(),
            feishu_ca_bundle=os.getenv("FEISHU_CA_BUNDLE", "").strip(),
            bitable_app_token=os.getenv("FEISHU_BITABLE_APP_TOKEN", "").strip(),
            bitable_table_id=os.getenv("FEISHU_BITABLE_TABLE_ID", "").strip(),
            bitable_url=os.getenv("FEISHU_BITABLE_URL", "").strip(),
            chat_id=os.getenv("FEISHU_CHAT_ID", "").strip(),
            http_timeout=float(os.getenv("HTTP_TIMEOUT", "20")),
            max_retries=get_int("MAX_RETRIES", 3),
            retry_backoff=float(os.getenv("RETRY_BACKOFF", "1.5")),
            page_timeout_ms=get_int("PAGE_TIMEOUT_MS", 60_000),
        )

        if cfg.top_n < 1:
            raise ConfigError("TOP_N 必须 >= 1。", "请检查 .env 中的 TOP_N。")
        return cfg

    def validate_for_write(self) -> None:
        """写库与推送前校验必要配置，缺失时给出定位方向。"""
        missing: list[str] = []
        if not self.feishu_app_id:
            missing.append("FEISHU_APP_ID")
        if not self.feishu_app_secret:
            missing.append("FEISHU_APP_SECRET")
        if not self.bitable_app_token:
            missing.append("FEISHU_BITABLE_APP_TOKEN")
        if not self.bitable_table_id:
            missing.append("FEISHU_BITABLE_TABLE_ID")
        if not self.chat_id:
            missing.append("FEISHU_CHAT_ID")
        if missing:
            raise ConfigError(
                "缺少飞书相关配置：" + ", ".join(missing),
                "请复制 config.example.env 为 .env，并填入你的测试企业凭证与资源标识。",
            )
