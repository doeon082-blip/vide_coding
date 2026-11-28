// 상태 객체 하나와 그것을 바꾸는 함수들. 화면은 상태를 보고 render(state)가 통째로 다시 그린다.
// 상태 변경 함수는 모두 '새 객체를 돌려주는 순수 함수'라서 시험이 쉽다.
// 대화 기록(messages)은 이 페이지의 메모리에만 있다: 브라우저 저장소·서버에 남기지 않고, 새로고침하거나 '새 대화'를 누르면 사라진다.
// 채산은 질문마다 따로 답한다(이전 대화를 기억하지 않는다). 그래서 이 기록은 '화면에 보여 주는 로그'일 뿐 서버로 보내지 않는다.

import { defaultView } from "./view-model.js";

/** phase: idle | loading. messages: [{ id, role: "user", text } | { id, role: "bot", vm, source, expanded, view }] */
export function initialState({ offline = false } = {}) {
  return { phase: "idle", step: 0, messages: [], nextId: 1, offline };
}

const append = (s, message) => ({ ...s, messages: [...s.messages, { id: s.nextId, ...message }], nextId: s.nextId + 1 });

/** 질문을 대화에 더하고 '답을 찾는 중'으로. */
export const addQuestion = (s, text) => ({ ...append(s, { role: "user", text }), phase: "loading", step: 0 });

/** 진행 단계(0~2)는 질문 중에만 바꾼다(늦게 도착한 타이머가 답 화면을 건드리지 않게). */
export const setStep = (s, step) => (s.phase === "loading" ? { ...s, step } : s);

/** 답(또는 실패 카드)을 대화에 더한다. source: { kind: "live" } | { kind: "example", generatedAt } | null */
export const addAnswer = (s, vm, source = null) => ({
  ...append(s, { role: "bot", vm, source, expanded: false, answerOpen: false, view: defaultView(vm) }),
  phase: "idle",
  step: 0,
});

const patch = (s, id, change) => ({ ...s, messages: s.messages.map((m) => (m.id === id && m.role === "bot" ? { ...m, ...change(m) } : m)) });

export const toggleRows = (s, id) => patch(s, id, (m) => ({ expanded: !m.expanded }));

export const toggleAnswer = (s, id) => patch(s, id, (m) => ({ answerOpen: !m.answerOpen }));

export const setView = (s, id, view) => patch(s, id, () => ({ view: view === "table" ? "table" : "chart" }));

/** 새 대화: 질문 중에는 비우지 않는다(늦게 올 답이 빈 화면에 붙는 것을 막는다). */
export const clearChat = (s) => (s.phase === "loading" ? s : { ...s, messages: [] });

/** 아주 작은 저장소: 상태를 바꾸면 구독한 함수를 부른다. */
export function createStore(initial) {
  let state = initial;
  const listeners = new Set();
  return {
    get: () => state,
    update(change) {
      state = change(state);
      for (const fn of listeners) fn(state);
    },
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
  };
}
