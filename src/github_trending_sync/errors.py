"""自定义异常体系。

所有可预期失败都抛出带明确信息的异常，由入口统一捕获并输出排查方向，
最终以非零退出码结束，避免“静默成功”。
"""


class SyncError(Exception):
    """任务级基础异常，携带面向使用者的排查提示。"""

    def __init__(self, message: str, hint: str = ""):
        self.message = message
        self.hint = hint
        super().__init__(message)


class ConfigError(SyncError):
    """配置或凭证缺失/非法。"""


class ScrapeError(SyncError):
    """页面采集失败（不可访问、无记录、结构变化等）。"""


class FeishuAuthError(SyncError):
    """飞书鉴权失败（app_id/app_secret 错误、权限不足等）。"""


class FeishuApiError(SyncError):
    """飞书业务接口错误（字段类型错误、限流、超时等）。"""
