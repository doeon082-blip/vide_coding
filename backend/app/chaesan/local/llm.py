"""LLM 어댑터: Ollama(내 컴퓨터)와 Cloudflare Workers AI(서비스) 둘 다 OpenAI 호환 `/chat/completions` 주소를 쓴다.

LLM 제공사마다 도구 호출(tool calling) 형식이 달라서 쓰지 않고, 응답을 JSON 스키마로 고정(response_format)한 뒤
core가 검사한다(core.guard.parse_guarded_json). 그래서 제공사를 바꿔도 이 파일만 바뀐다.
오류 상세(내부 주소·모델 이름·응답 본문)와 비밀값(API 토큰)은 로그에도 남기지 않고 LLMError에는 일반 문장만 담는다.

어느 쪽을 쓸지는 환경변수 `LLM_PROVIDER`(ollama | workers_ai, 기본 ollama)로 정한다 → `make_llm()`.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Final

import httpx

from app.chaesan.core.config import LOCAL_MODEL
from app.chaesan.core.ports import LLM, LLMError, LLMResult

logger = logging.getLogger(__name__)
# httpx는 INFO 단계에서 요청 주소 전체를 로그에 남긴다. Workers AI 주소에는 계정 ID가 들어 있으므로 경고 이상만 남게 한다.
for _noisy in ("httpx", "httpcore"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
PUBLIC_ERROR: Final = "AI 서비스를 일시적으로 사용할 수 없습니다."
# 참고(측정): 프롬프트가 같으면 온도 0에서 출력이 같다(seed 유무와 무관).
# 같은 질문의 결과가 실행마다 달라지는 것은 프롬프트에 매번 새로 넣는 1회용 난수(데이터 구분자 nonce, 유출 감지 canary) 때문이다.
# 보안 장치라 없애지 않으므로 정확도는 3회 반복의 범위로 잰다.

# Cloudflare Workers AI: 로컬에서 튜닝한 gemma4 26B와 같은 계열의 모델(Neurons 소모는 대시보드에서 확인).
WORKERS_AI_MODEL: Final = "@cf/google/gemma-4-26b-a4b-it"
_ACCOUNT_ID = re.compile(
    r"[0-9a-f]{32}"
)  # Cloudflare 계정 ID 모양. 주소에 끼워 넣기 전에 검사해 엉뚱한 값이 주소를 바꾸지 못하게 한다
_MODEL_NAME = re.compile(r"@?[A-Za-z0-9._\-]+(?:/[A-Za-z0-9._\-]+)*")


async def _complete(
    url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float, transport: httpx.AsyncBaseTransport | None
) -> LLMResult:
    """OpenAI 호환 /chat/completions를 한 번 부르고 (본문, 입력 토큰, 출력 토큰)을 돌려준다. 실패는 LLMError(일반 문장)."""
    try:
        async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            body = resp.json()
        text = body["choices"][0]["message"]["content"] or ""
        usage = body.get("usage") or {}
    except httpx.HTTPStatusError as exc:
        # 상태 코드만 남긴다(401=토큰 문제, 429=한도, 5xx=상대 서버). 본문·주소·헤더는 남기지 않는다.
        logger.warning("llm call failed: HTTP %s", exc.response.status_code)
        raise LLMError(PUBLIC_ERROR) from exc
    except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
        logger.warning("llm call failed: %s", type(exc).__name__)
        raise LLMError(PUBLIC_ERROR) from exc
    return LLMResult(text, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)))


class OllamaLLM:
    """내 컴퓨터의 Ollama(OpenAI 호환 주소). 개발·로컬 시연용."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str = LOCAL_MODEL,
        timeout: float | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base = (base_url or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
        self._model = model
        self._timeout = timeout or float(os.getenv("OLLAMA_TIMEOUT") or 180)
        self._transport = transport  # 테스트에서 가짜 서버를 끼우는 자리

    async def chat_json(
        self, system: str, user: str, schema: dict[str, Any], *, max_tokens: int, temperature: float
    ) -> LLMResult:
        payload = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "temperature": temperature,
            "max_tokens": max_tokens,
            # gemma4는 추론(reasoning) 모델이라 답 전에 생각 토큰을 길게 써서 max_tokens에 걸려 JSON이 잘렸다(실제 측정:
            # 계획 단계가 500토큰에서 두 번 다 잘림). 생각을 끄면 응답이 2초 → 0.3초로 줄고 토큰도 준다.
            "reasoning_effort": "none",
            "response_format": {"type": "json_schema", "json_schema": {"name": "chaesan", "strict": True, "schema": schema}},
        }
        return await _complete(f"{self._base}/v1/chat/completions", {}, payload, self._timeout, self._transport)


class WorkersAILLM:
    """Cloudflare Workers AI(OpenAI 호환 주소). 서비스용: 내 컴퓨터를 켜 두지 않아도 된다.

    계정 ID와 API 토큰은 환경변수(CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN)에서만 읽는다(코드·git에 두지 않는다).
    무료 한도는 하루 10,000 Neurons(00:00 UTC에 초기화). 넘으면 429가 오고, 화면은 예시 답으로 안내한다.
    """

    def __init__(
        self,
        account_id: str | None = None,
        api_token: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        account = (account_id or os.getenv("CLOUDFLARE_ACCOUNT_ID") or "").strip()
        token = (api_token or os.getenv("CLOUDFLARE_API_TOKEN") or "").strip()
        name = (model or os.getenv("CLOUDFLARE_AI_MODEL") or WORKERS_AI_MODEL).strip()
        # 값은 오류 문장에 넣지 않는다(비밀값이 로그에 남지 않게).
        if not _ACCOUNT_ID.fullmatch(account):
            raise ValueError("CLOUDFLARE_ACCOUNT_ID가 비었거나 형식이 맞지 않습니다(영문 소문자·숫자 32자).")
        if not token:
            raise ValueError("CLOUDFLARE_API_TOKEN이 비어 있습니다.")
        if not _MODEL_NAME.fullmatch(name):
            raise ValueError("CLOUDFLARE_AI_MODEL 형식이 맞지 않습니다.")
        self._url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions"
        self._headers = {"Authorization": f"Bearer {token}"}
        self._model = name
        self._timeout = timeout or float(os.getenv("CLOUDFLARE_AI_TIMEOUT") or 60)
        self._transport = transport

    def __repr__(self) -> str:  # 로그·오류 출력에 토큰이 딸려 나오지 않게
        return f"WorkersAILLM(model={self._model!r})"

    async def chat_json(
        self, system: str, user: str, schema: dict[str, Any], *, max_tokens: int, temperature: float
    ) -> LLMResult:
        payload = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            # Workers AI JSON 모드: json_schema에 스키마 자체를 넣는다(공식 문서 형식).
            "response_format": {"type": "json_schema", "json_schema": schema},
        }
        return await _complete(self._url, self._headers, payload, self._timeout, self._transport)


def make_llm() -> LLM:
    """환경변수 LLM_PROVIDER(ollama | workers_ai, 기본 ollama)에 따라 LLM 어댑터를 만든다. 설정이 틀리면 시작할 때 바로 멈춘다."""
    provider = (os.getenv("LLM_PROVIDER") or "ollama").strip().lower()
    if provider == "ollama":
        return OllamaLLM()
    if provider == "workers_ai":
        return WorkersAILLM()
    raise ValueError("LLM_PROVIDER는 ollama 또는 workers_ai여야 합니다.")
