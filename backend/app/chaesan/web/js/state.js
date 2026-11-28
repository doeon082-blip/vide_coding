// 상태 객체 하나와 그것을 바꾸는 함수들. 화면은 상태를 보고 render(state)가 통째로 다시 그린다.
// 상태 변경 함수는 모두 '새 객체를 돌려주는 순수 함수'라서 시험이 쉽다. 질문 원문은 상태에 두지 않는다(저장하지 않는다는 약속).

/** phase: idle(처음) | loading(질문 중) | done(답) | error(실패). source: null | {kind:"live"} | {kind:"example", generatedAt} */
export function initialState({ offline = false } = {}) {
  return { phase: "idle", step: 0, result: null, source: null, expanded: false, offline };
}

export const setLoading = (s) => ({ ...s, phase: "loading", step: 0, result: null, source: null, expanded: false });

/** 진행 단계(0~2)는 질문 중에만 바꾼다(늦게 도착한 타이머가 답 화면을 건드리지 않게). */
export const setStep = (s, step) => (s.phase === "loading" ? { ...s, step } : s);

export const setAnswer = (s, result, source) => ({ ...s, phase: "done", step: 0, result, source, expanded: false });

export const setError = (s, result) => ({ ...s, phase: "error", step: 0, result, source: null, expanded: false });

export const toggleRows = (s) => ({ ...s, expanded: !s.expanded });

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
