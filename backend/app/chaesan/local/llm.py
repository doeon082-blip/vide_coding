"""로컬 LLM 어댑터: Ollama의 OpenAI 호환 주소(/v1/chat/completions).

LLM 제공사마다 도구 호출(tool calling) 형식이 달라서 쓰지 않고, 응답을 JSON 스키마로 고정(response_format)한 뒤
core가 검사한다(core.guard.parse_guarded_json). 이렇게 하면 서비스(Workers AI)로 바꿀 때 이 파일만 바뀐다.
오류 상세(내부 주소·모델 이름·응답 본문)는 로그에만 남기고 LLMError에는 일반 문장만 담는다.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from app.chaesan.core.config import LOCAL_MODEL
from app.chaesan.core.ports import LLMError, LLMResult

logger = logging.getLogger(__name__)
PUBLIC_ERROR = "AI 서비스를 일시적으로 사용할 수 없습니다."
# 참고(측정): 프롬프트가 같으면 온도 0에서 출력이 같다(seed 유무와 무관).
# 같은 질문의 결과가 실행마다 달라지는 것은 프롬프트에 매번 새로 넣는 1회용 난수(데이터 구분자 nonce, 유출 감지 canary) 때문이다.
# 보안 장치라 없애지 않으므로 정확도는 3회 반복의 범위로 잰다.


class OllamaLLM:
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
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                resp = await client.post(f"{self._base}/v1/chat/completions", json=payload)
                resp.raise_for_status()
                body = resp.json()
            text = body["choices"][0]["message"]["content"] or ""
            usage = body.get("usage") or {}
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            logger.warning("ollama call failed: %s", type(exc).__name__)
            raise LLMError(PUBLIC_ERROR) from exc
        return LLMResult(text, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)))
