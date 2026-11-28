// 서버 호출 시험: 가짜 fetch로 오류 분류·시간 제한·요청 모양을 확인한다.
import assert from "node:assert/strict";
import test from "node:test";
import { askServer, classifyHttp } from "../app/chaesan/web/js/api.js";

const reply = (status, body) => async () => ({ ok: status >= 200 && status < 300, status, json: async () => body });

test("HTTP 상태 분류", () => {
  assert.deepEqual([400, 422, 429, 503, 500, 404].map(classifyHttp), ["blocked", "invalid", "rate", "busy", "server", "server"]);
});

test("성공은 data를 그대로 돌려준다", async () => {
  const r = await askServer("질문", { fetchImpl: reply(200, { answer: "a" }) });
  assert.deepEqual(r, { ok: true, data: { answer: "a" } });
});

test("오류는 종류와 서버의 문자열 detail만 전달(422의 검증 목록은 버림)", async () => {
  assert.deepEqual(await askServer("q", { fetchImpl: reply(429, { detail: "너무 많아요" }) }), { ok: false, kind: "rate", detail: "너무 많아요" });
  assert.equal((await askServer("q", { fetchImpl: reply(422, { detail: [{ loc: ["body"] }] }) })).detail, null);
  const notJson = async () => ({ ok: false, status: 502, json: async () => { throw new Error("x"); } });
  assert.deepEqual(await askServer("q", { fetchImpl: notJson }), { ok: false, kind: "server", detail: null });
});

test("네트워크 오류·시간 초과를 구분한다", async () => {
  const down = async () => { throw new TypeError("fetch failed"); };
  assert.equal((await askServer("q", { fetchImpl: down })).kind, "network");
  const hang = (_url, { signal }) => new Promise((_, reject) => signal.addEventListener("abort", () => reject(Object.assign(new Error("a"), { name: "AbortError" }))));
  assert.equal((await askServer("q", { fetchImpl: hang, timeoutMs: 20 })).kind, "timeout");
});

test("요청은 POST JSON이고 쿠키·referrer를 보내지 않는다", async () => {
  let seen;
  await askServer("안녕", { fetchImpl: async (url, init) => { seen = { url, init }; return { ok: true, status: 200, json: async () => ({}) }; } });
  assert.equal(seen.url, "api/chaesan/ask");
  assert.equal(seen.init.method, "POST");
  assert.equal(seen.init.body, JSON.stringify({ question: "안녕" }));
  assert.equal(seen.init.credentials, "omit");
  assert.equal(seen.init.referrerPolicy, "no-referrer");
});
