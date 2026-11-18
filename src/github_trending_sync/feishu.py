"""飞书开放平台客户端。

封装：
- tenant_access_token 获取与缓存
- 多维表格（Bitable）记录读取 / 创建 / 更新
- 群消息发送

统一处理超时、限流与接口错误，失败抛出带排查方向的异常。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import requests

from .errors import FeishuApiError, FeishuAuthError

# 需要退避重试的限流/服务端错误
_RETRYABLE_CODES = {429, 500, 502, 503, 504, 99991400}
# 鉴权/权限类错误码（token 失效、app 无效、权限不足等）
_AUTH_ERROR_CODES = {99991661, 99991662, 99991663, 99991664, 99991668, 99991669, 99991672}


@dataclass
class FeishuClient:
    app_id: str
    app_secret: str
    base_url: str = "https://open.feishu.cn"
    http_timeout: float = 20.0
    max_retries: int = 3
    retry_backoff: float = 1.5
    # 可选：自定义 CA 证书文件路径（受限内网代理等场景）。留空则使用默认验证。
    ca_bundle: str = ""

    _token: str = field(default="", init=False, repr=False)
    _token_expire_at: float = field(default=0.0, init=False, repr=False)

    def _verify(self):
        """返回 requests 的 verify 取值：True / CA 文件路径 / False。"""
        if self.ca_bundle:
            if self.ca_bundle.strip().lower() in ("false", "0", "off", "no"):
                return False
            return self.ca_bundle
        return True

    # ---------- 鉴权 ----------
    def get_token(self) -> str:
        if self._token and time.time() < self._token_expire_at - 60:
            return self._token
        url = f"{self.base_url}/open-apis/auth/v3/tenant_access_token/internal"
        try:
            resp = requests.post(
                url,
                json={"app_id": self.app_id, "app_secret": self.app_secret},
                timeout=self.http_timeout,
                verify=self._verify(),
            )
        except requests.RequestException as exc:
            raise FeishuApiError(
                f"获取 tenant_access_token 网络失败：{exc}",
                "请检查网络与 FEISHU_BASE_URL 配置。",
            ) from exc

        data = resp.json()
        if data.get("code") != 0:
            raise FeishuAuthError(
                f"飞书鉴权失败：code={data.get('code')} msg={data.get('msg')}",
                "请核对 FEISHU_APP_ID / FEISHU_APP_SECRET，确认应用已启用且具备权限。",
            )
        self._token = data["tenant_access_token"]
        self._token_expire_at = time.time() + int(data.get("expire", 7200))
        return self._token

    # ---------- 底层请求（重试 + 错误归一） ----------
    def _request(self, method: str, path: str, *, params=None, json_body=None):
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self.get_token()}",
            "Content-Type": "application/json; charset=utf-8",
        }
        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = requests.request(
                    method, url, params=params, json=json_body,
                    headers=headers, timeout=self.http_timeout,
                    verify=self._verify(),
                )
            except requests.RequestException as exc:
                last_err = exc
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_backoff * (attempt + 1))
                    continue
                raise FeishuApiError(
                    f"飞书接口网络错误：{exc}",
                    "请检查网络连通性与 FEISHU_BASE_URL。",
                ) from exc

            status = resp.status_code
            try:
                payload = resp.json()
            except ValueError:
                payload = {}

            code = payload.get("code", status)

            # 成功
            if status == 200 and code == 0:
                return payload

            # 限流/服务端错误 -> 退避重试
            if status in _RETRYABLE_CODES or code in _RETRYABLE_CODES:
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_backoff * (attempt + 1))
                    last_err = FeishuApiError(
                        f"飞书接口限流/暂不可用：code={code} msg={payload.get('msg')}",
                        "已自动重试；若持续失败请稍后重跑或降低频率。",
                    )
                    continue

            # 鉴权类错误
            if code in _AUTH_ERROR_CODES:
                raise FeishuAuthError(
                    f"飞书接口鉴权/权限错误：code={code} msg={payload.get('msg')}",
                    "请确认应用已获得 bitable 与 im 权限，且已加入多维表格协作与群。",
                )

            # 其余业务错误
            raise FeishuApiError(
                f"飞书接口错误：code={code} msg={payload.get('msg')} path={path}",
                "请根据错误码核对字段类型、资源标识与应用权限。",
            )

        raise FeishuApiError(str(last_err) if last_err else "未知错误")

    # ---------- 多维表格 ----------
    def list_records(self, app_token: str, table_id: str) -> list[dict]:
        """读取表格全部记录（自动分页），返回 [{record_id, fields}]。"""
        items: list[dict] = []
        page_token: str | None = None
        while True:
            params: dict = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            payload = self._request(
                "GET",
                f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
                params=params,
            )
            data = payload.get("data", {})
            items.extend(data.get("items", []))
            if data.get("has_more"):
                page_token = data.get("page_token")
            else:
                break
        return items

    def create_record(self, app_token: str, table_id: str, fields: dict) -> dict:
        payload = self._request(
            "POST",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            json_body={"fields": fields},
        )
        return payload.get("data", {}).get("record", {})

    def update_record(self, app_token: str, table_id: str, record_id: str, fields: dict) -> dict:
        payload = self._request(
            "PUT",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
            json_body={"fields": fields},
        )
        return payload.get("data", {}).get("record", {})

    # ---------- 群消息 ----------
    def send_text(self, chat_id: str, text: str) -> dict:
        payload = self._request(
            "POST",
            "/open-apis/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            json_body={
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        )
        return payload.get("data", {})
