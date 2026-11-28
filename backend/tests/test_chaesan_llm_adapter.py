"""Ollama 어댑터 테스트(가짜 서버): 요청 모양, 토큰 수 읽기, 오류를 일반 문장으로 바꾸기."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from app.chaesan.core.ports import LLMError
from app.chaesan.local.llm import PUBLIC_ERROR, OllamaLLM

SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}


def llm(handler: Any) -> OllamaLLM:
    return OllamaLLM("http://ollama.test:11434/", transport=httpx.MockTransport(handler))


def call(client: OllamaLLM) -> Any:
    return asyncio.run(client.chat_json("시스템", "사용자", SCHEMA, max_tokens=123, temperature=0.2))


def test_request_shape_and_token_usage() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"a":"b"}'}}], "usage": {"prompt_tokens": 7, "completion_tokens": 3}}
        )

    res = call(llm(handler))
    assert (res.text, res.input_tokens, res.output_tokens) == ('{"a":"b"}', 7, 3)
    assert seen["url"] == "http://ollama.test:11434/v1/chat/completions"
    body = seen["body"]
    assert body["max_tokens"] == 123
    assert body["temperature"] == 0.2
    assert body["stream"] is False
    assert body["reasoning_effort"] == "none"  # 생각 토큰이 JSON을 잘라 먹지 않게
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA
    assert [m["role"] for m in body["messages"]] == ["system", "user"]


def test_missing_usage_is_zero() -> None:
    res = call(llm(lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})))
    assert (res.input_tokens, res.output_tokens) == (0, 0)


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx.Response(500, text="secret internal stack http://ollama.test gemma4:26b"),
        lambda r: httpx.Response(200, text="not json"),
        lambda r: httpx.Response(200, json={"choices": []}),
        lambda r: httpx.Response(200, json={"nope": 1}),
        lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused http://ollama.test")),
        lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow")),
    ],
)
def test_failures_become_a_generic_llm_error(handler: Any) -> None:
    with pytest.raises(LLMError) as err:
        call(llm(handler))
    assert str(err.value) == PUBLIC_ERROR  # 내부 주소·모델 이름·응답 본문이 새지 않는다
