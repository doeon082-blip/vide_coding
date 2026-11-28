// 상태 변경 시험: 새 객체를 돌려주고, 늦게 온 타이머가 답 화면을 건드리지 못하는지.
import assert from "node:assert/strict";
import test from "node:test";
import { createStore, initialState, setAnswer, setError, setLoading, setStep, toggleRows } from "../app/chaesan/web/js/state.js";

test("질문 중에만 단계를 바꾼다", () => {
  const s0 = initialState();
  assert.equal(setStep(s0, 2), s0); // idle에서는 그대로(같은 객체)
  const loading = setLoading(s0);
  assert.equal(setStep(loading, 2).step, 2);
  const done = setAnswer(loading, { answer: "a" }, { kind: "live" });
  assert.equal(setStep(done, 2), done);
});

test("질문을 새로 시작하면 이전 답·펼침이 사라진다", () => {
  let s = setAnswer(initialState(), { answer: "a" }, { kind: "live" });
  s = toggleRows(s);
  assert.equal(s.expanded, true);
  s = setLoading(s);
  assert.deepEqual([s.phase, s.result, s.expanded, s.source], ["loading", null, false, null]);
});

test("setError는 phase를 error로", () => {
  assert.equal(setError(initialState(), { answer: "x" }).phase, "error");
});

test("상태에 질문 원문 칸이 없다(비저장 약속)", () => {
  assert.equal(Object.keys(initialState()).some((k) => /question|query|text/i.test(k)), false);
});

test("저장소: 바꾸면 구독자에게 알리고, 해제하면 알리지 않는다", () => {
  const store = createStore(initialState());
  const seen = [];
  const off = store.subscribe((s) => seen.push(s.phase));
  store.update(setLoading);
  off();
  store.update((s) => setAnswer(s, {}, null));
  assert.deepEqual(seen, ["loading"]);
  assert.equal(store.get().phase, "done");
});
