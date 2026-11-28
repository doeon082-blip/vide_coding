"""LLM 연결 점검: 설정된 LLM(LLM_PROVIDER)을 짧은 JSON 요청 한 번으로 시험한다. 비밀값·주소는 출력하지 않는다.

실행: `uv run --env-file .env python -m eval.smoke_llm` (backend/ 에서)
확인하는 것: 인증이 되는가, JSON 모드가 스키마대로 나오는가, 걸린 시간, 입력·출력 토큰 수(하루 한도 가늠용).
"""

from __future__ import annotations

import asyncio
import json
import time

from app.chaesan.core.ports import LLMError
from app.chaesan.local.llm import make_llm

SCHEMA = {
    "type": "object",
    "properties": {"intent": {"type": "string", "enum": ["history", "facility", "news", "org", "data", "unknown"]}, "ok": {"type": "boolean"}},
    "required": ["intent", "ok"],
}


async def main() -> None:
    llm = make_llm()
    print("모델:", getattr(llm, "label", "?"))
    started = time.perf_counter()
    try:
        res = await llm.chat_json(
            "질문의 갈래를 JSON으로만 답한다.",
            "올림픽공원 주차장은 몇 시에 가장 붐벼?",
            SCHEMA,
            max_tokens=100,
            temperature=0.0,
        )
    except LLMError as exc:
        print("실패:", exc, "(원인 상세는 서버 로그의 상태 코드를 본다)")
        raise SystemExit(1) from exc
    elapsed = time.perf_counter() - started
    print(f"성공: {elapsed:.2f}초, 입력 {res.input_tokens}토큰, 출력 {res.output_tokens}토큰")
    print("응답:", res.text[:200])
    data = json.loads(res.text)
    assert set(data) == {"intent", "ok"}, "스키마 밖의 키가 있다"
    print("JSON 스키마 확인: 통과")


if __name__ == "__main__":
    asyncio.run(main())
