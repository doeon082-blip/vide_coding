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


# --------------------------------------------------------------------------- Cloudflare Workers AI

from app.chaesan.local.llm import WORKERS_AI_MODEL, WorkersAILLM, make_llm  # noqa: E402

ACCOUNT = "0123456789abcdef0123456789abcdef"
TOKEN = "test-token-DO-NOT-LEAK"  # noqa: S105 (시험용 가짜 값)


def workers(handler: Any, **kw: Any) -> WorkersAILLM:
    return WorkersAILLM(ACCOUNT, TOKEN, transport=httpx.MockTransport(handler), **kw)


def test_workers_request_shape_and_auth() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"a":"b"}'}}], "usage": {"prompt_tokens": 11, "completion_tokens": 4}}
        )

    res = call(workers(handler))  # type: ignore[arg-type]
    assert (res.text, res.input_tokens, res.output_tokens) == ('{"a":"b"}', 11, 4)
    assert seen["url"] == f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/ai/v1/chat/completions"
    assert seen["auth"] == f"Bearer {TOKEN}"
    body = seen["body"]
    assert body["model"] == WORKERS_AI_MODEL == "@cf/google/gemma-4-26b-a4b-it"
    assert body["max_tokens"] == 123 and body["temperature"] == 0.2
    assert body["response_format"] == {"type": "json_schema", "json_schema": SCHEMA}  # Workers AI 문서 형식: 스키마 자체
    assert "reasoning_effort" not in body and "stream" not in body
    assert [m["role"] for m in body["messages"]] == ["system", "user"]


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 502, 503])
def test_workers_http_errors_become_generic_and_never_leak_secrets(status: int, caplog: pytest.LogCaptureFixture) -> None:
    body = f"internal detail {TOKEN} {ACCOUNT} JSON Mode couldn't be met"
    with caplog.at_level("DEBUG"), pytest.raises(LLMError) as err:
        call(workers(lambda r: httpx.Response(status, text=body)))  # type: ignore[arg-type]
    assert str(err.value) == PUBLIC_ERROR
    logged = caplog.text
    assert TOKEN not in logged and ACCOUNT not in logged and "internal detail" not in logged
    assert str(status) in logged  # 원인 파악용으로 상태 코드만 남는다


def test_workers_network_error_is_generic() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"refused {request.url}")

    with pytest.raises(LLMError) as err:
        call(workers(boom))  # type: ignore[arg-type]
    assert str(err.value) == PUBLIC_ERROR  # 주소(계정 ID가 든)는 오류 문장에 들어가지 않는다
    assert ACCOUNT not in str(err.value) and TOKEN not in str(err.value)


def test_workers_config_is_validated_without_echoing_values() -> None:
    for bad in ("", "short", ACCOUNT.upper(), ACCOUNT + "0", "../../evil/" + ACCOUNT[:20], "g" * 32):
        with pytest.raises(ValueError, match="CLOUDFLARE_ACCOUNT_ID") as err:
            WorkersAILLM(bad, TOKEN)
        assert bad not in str(err.value) or bad == ""
    with pytest.raises(ValueError, match="CLOUDFLARE_API_TOKEN"):
        WorkersAILLM(ACCOUNT, " ")
    with pytest.raises(ValueError, match="CLOUDFLARE_AI_MODEL"):
        WorkersAILLM(ACCOUNT, TOKEN, "bad model; DROP")


def test_workers_repr_hides_the_token() -> None:
    client = WorkersAILLM(ACCOUNT, TOKEN)
    assert TOKEN not in repr(client) and TOKEN not in str(client) and ACCOUNT not in repr(client)


def test_make_llm_selects_by_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert isinstance(make_llm(), OllamaLLM)  # 기본은 Ollama
    monkeypatch.setenv("LLM_PROVIDER", "workers_ai")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACCOUNT)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", TOKEN)
    assert isinstance(make_llm(), WorkersAILLM)
    monkeypatch.setenv("LLM_PROVIDER", "Workers_AI ")  # 대소문자·공백은 너그럽게
    assert isinstance(make_llm(), WorkersAILLM)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        make_llm()
    monkeypatch.setenv("LLM_PROVIDER", "workers_ai")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "")
    with pytest.raises(ValueError, match="CLOUDFLARE_ACCOUNT_ID"):  # 설정이 비면 조용히 넘어가지 않고 시작할 때 멈춘다
        make_llm()
