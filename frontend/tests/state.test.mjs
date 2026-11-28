// 상태 변경 시험: 새 객체를 돌려주고, 늦게 온 타이머가 답 화면을 건드리지 못하는지.
import assert from "node:assert/strict";
import test from "node:test";
import { addAnswer, addQuestion, clearChat, createStore, initialState, setStep, setView, toggleAnswer, toggleRows } from "../js/state.js";
import { toViewModel } from "../js/view-model.js";

const vm = (extra = {}) => toViewModel({ status: "answered", answer: "a", ...extra });
const chartRows = [{ hour: 1, n: 5 }, { hour: 2, n: 9 }, { hour: 3, n: 2 }];

test("질문을 더하면 '찾는 중'이 되고, 답을 더하면 끝난다", () => {
  let s = addQuestion(initialState(), "안녕");
  assert.deepEqual([s.phase, s.messages.length, s.messages[0].role], ["loading", 1, "user"]);
  s = addAnswer(s, vm(), { kind: "live" });
  assert.deepEqual([s.phase, s.messages.length, s.messages[1].role], ["idle", 2, "bot"]);
  assert.notEqual(s.messages[0].id, s.messages[1].id);
});

test("진행 단계는 질문 중에만 바꾼다", () => {
  const s0 = initialState();
  assert.equal(setStep(s0, 2), s0);
  const loading = addQuestion(s0, "q");
  assert.equal(setStep(loading, 2).step, 2);
  const done = addAnswer(loading, vm());
  assert.equal(setStep(done, 2), done);
});

test("그래프를 그릴 수 있으면 처음 보기가 그래프, 아니면 표", () => {
  assert.equal(addAnswer(initialState(), vm({ evidence_rows: chartRows })).messages[0].view, "chart");
  assert.equal(addAnswer(initialState(), vm({ evidence_rows: [{ a: 1 }] })).messages[0].view, "table");
});

test("그래프·표 전환과 더 보기는 해당 답에만 적용된다", () => {
  let s = addAnswer(addAnswer(initialState(), vm({ evidence_rows: chartRows })), vm({ evidence_rows: chartRows }));
  const [a, b] = s.messages;
  s = setView(s, a.id, "table");
  s = toggleRows(s, b.id);
  assert.deepEqual([s.messages[0].view, s.messages[1].view], ["table", "chart"]);
  assert.deepEqual([s.messages[0].expanded, s.messages[1].expanded], [false, true]);
  assert.equal(setView(s, a.id, "weird").messages[0].view, "chart"); // 알 수 없는 값은 그래프로
});

test("새 대화: 질문 중에는 비우지 않고, 아니면 비운다", () => {
  const loading = addQuestion(initialState(), "q");
  assert.equal(clearChat(loading), loading);
  const done = addAnswer(loading, vm());
  assert.equal(clearChat(done).messages.length, 0);
});

test("상태 변경은 원래 객체를 바꾸지 않는다", () => {
  const s = initialState();
  addQuestion(s, "q");
  assert.equal(s.messages.length, 0);
});

test("저장소: 바꾸면 구독자에게 알리고, 해제하면 알리지 않는다", () => {
  const store = createStore(initialState());
  const seen = [];
  const off = store.subscribe((s) => seen.push(s.phase));
  store.update((s) => addQuestion(s, "q"));
  off();
  store.update((s) => addAnswer(s, vm()));
  assert.deepEqual(seen, ["loading"]);
  assert.equal(store.get().phase, "idle");
});

test("긴 답 펼침은 해당 답에만 적용된다", () => {
  let s = addAnswer(addAnswer(initialState(), vm()), vm());
  s = toggleAnswer(s, s.messages[0].id);
  assert.deepEqual(s.messages.map((m) => m.answerOpen), [true, false]);
});
