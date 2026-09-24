"""``aipd_os.net.http`` —— src/ 侧唯一的 HTTP 出口（标准库 urllib）。

收敛背景：迁移前 HEAD 上 src/ 共 **9 个 HTTP 出口调用点**（由 ``git grep`` 现算，
分布在 7 个模块）——7 处 ``urllib.request.urlopen``（llm 1、researchstudio 2、
research_adapter 1、imggen 2、visual_audit 1）、2 处 ``requests.post``
（``evals/runner.py`` 与 ``evals_runner/completion.py``），另有 1 处脚本内
``requests``+urllib3 适配器。分散实现导致同一件事有 8 个版本：超时口径不一、
没有退避、`scheme` 白名单靠三处 `# noqa: S310` 注释手工豁免。

选型（**事后补记**的候选比较，完整六维表见
docs/audit/NET_EGRESS_CONVERGENCE_2026-09-24.md §3）：
* 标准库 urllib —— 不新增运行时依赖，与「默认安装保持最小」的既有约束一致 ✅ 选用
* ``requests`` + urllib3 ``Retry``（脚本连接器仍用它）—— 功能更全，但
  ``requests`` 在本仓是 **optional extra**（``pyproject`` 的 ``full`` extra；
  本机实测 ``requests==2.32.5``、``urllib3==2.6.3``），把它变成核心 LLM 路径的
  硬依赖不划算——`evals_runner/completion.py` 迁移前正因如此要求 `full` 才跑得动
* ``httpx`` —— 本机未安装（实测 ``PackageNotFoundError``），且同样是新依赖

保留的语义（与脚本连接器一致，便于两条路径行为可比）：
- 只对**瞬态 HTTP 状态**重试（429/5xx），网络异常立即上抛——
  否则一个持续限流的端点能把进程挂死在重试循环里；
- ``Retry-After`` 支持秒数与 HTTP-date，退避有上限；
- 只允许 http/https scheme，其余在发出请求之前拒绝。

不接管：``scripts/research/_http_runtime.py``——它要给**第三方依赖自有的**
``requests.Session``（如 OpenReview）装策略，只能用 requests。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Callable

DEFAULT_TIMEOUT_S = 30.0
DEFAULT_MAX_ATTEMPTS = 1
DEFAULT_BACKOFF_BASE_S = 3.0
DEFAULT_BACKOFF_CAP_S = 60.0
MAX_BODY_READ_BYTES = 32 * 1024 * 1024

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
ALLOWED_SCHEMES = frozenset({"http", "https"})


class HttpError(RuntimeError):
    """请求无法完成（scheme 不合法 / 传输层失败 / 非可重试的 HTTP 状态）。"""


@dataclass(frozen=True)
class HttpResponse:
    """一次 HTTP 响应。非 2xx 也会正常返回（由调用方判定），便于保留状态码与正文。"""

    status: int
    headers: Any
    content: bytes

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text)

    def header(self, name: str) -> str:
        return self.headers.get(name, "") if self.headers is not None else ""


def retry_after_seconds(value: str | None) -> float | None:
    """解析 ``Retry-After``（秒数或 HTTP-date）；不可解析时返回 None。"""
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        # 合法值有两种形态（纯秒数 / HTTP-date）：前者解析失败不算错误，继续按日期解析
        try:
            when = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        return max(0.0, when.timestamp() - time.time())


def check_url(url: str) -> str:
    """scheme 白名单：不发请求就拒掉 file/ftp/data 之类。"""
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise HttpError(f"unsupported URL scheme {scheme!r} (allow http/https)")
    return url


def request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    json_body: Any = None,
    timeout: float = DEFAULT_TIMEOUT_S,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_base: float = DEFAULT_BACKOFF_BASE_S,
    backoff_cap: float = DEFAULT_BACKOFF_CAP_S,
    sleep: Callable[[float], None] = time.sleep,
) -> HttpResponse:
    """发一次（至多 ``max_attempts`` 次）HTTP 请求。

    :raises HttpError: scheme 不合法、传输层失败，或 ``json_body`` 无法序列化
    """
    check_url(url)
    payload = body
    sent_headers = dict(headers or {})
    if json_body is not None:
        payload = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        sent_headers.setdefault("Content-Type", "application/json")

    attempts = max(1, int(max_attempts))
    last: HttpResponse | None = None
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(url, data=payload,
                                     headers=sent_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return HttpResponse(status=resp.getcode(),
                                    headers=resp.headers,
                                    content=resp.read(MAX_BODY_READ_BYTES))
        except urllib.error.HTTPError as exc:      # 非 2xx：带状态码返回
            try:
                content = exc.read(MAX_BODY_READ_BYTES)
            except Exception:  # noqa: BLE001 - 响应体读不出也要如实返回状态
                content = b""
            last = HttpResponse(status=exc.code, headers=exc.headers,
                                content=content)
        except urllib.error.URLError as exc:
            raise HttpError(f"request to {url} failed: {exc.reason}") from exc
        except Exception as exc:  # noqa: BLE001 - 统一诚实上抛，不吞网络问题
            raise HttpError(f"request to {url} failed: {exc}") from exc

        assert last is not None
        if last.status not in RETRYABLE_STATUS_CODES or attempt >= attempts:
            return last
        delay = retry_after_seconds(last.header("Retry-After"))
        if delay is None:
            delay = backoff_base * (2 ** (attempt - 1))
        sleep(min(backoff_cap, max(0.0, delay)))

    raise HttpError("unreachable")              # pragma: no cover


def request_json(url: str, **kwargs: Any) -> Any:
    """``request`` + 解析 JSON；非 2xx 或解析失败都抛 :class:`HttpError`。"""
    resp = request(url, **kwargs)
    if not 200 <= resp.status < 300:
        raise HttpError(f"HTTP {resp.status}: {resp.text[:500]}")
    try:
        return resp.json()
    except ValueError as exc:
        raise HttpError(f"response is not JSON: {exc}") from exc


__all__ = [
    "ALLOWED_SCHEMES",
    "DEFAULT_BACKOFF_BASE_S",
    "DEFAULT_BACKOFF_CAP_S",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_TIMEOUT_S",
    "RETRYABLE_STATUS_CODES",
    "HttpError",
    "HttpResponse",
    "check_url",
    "request",
    "request_json",
    "retry_after_seconds",
]
