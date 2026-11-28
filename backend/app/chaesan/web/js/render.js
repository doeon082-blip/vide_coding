// render(state): 상태를 보고 결과 영역을 통째로 다시 그린다(조각을 하나씩 고치지 않는다 → 상태와 화면이 어긋나지 않는다).

import { exampleButton, progress, resultCard } from "./components.js";

/** 결과 영역(root)을 상태에 맞게 다시 그린다. handlers.onToggleRows: '더 보기' 단추. */
export function render(state, root, handlers) {
  root.setAttribute("aria-busy", state.phase === "loading" ? "true" : "false");
  if (state.phase === "loading") {
    root.replaceChildren(progress(state.step));
  } else if ((state.phase === "done" || state.phase === "error") && state.result) {
    root.replaceChildren(resultCard(state.result, { source: state.source, expanded: state.expanded, onToggleRows: handlers.onToggleRows }));
  } else {
    root.replaceChildren();
  }
}

/** 예시 질문 단추들을 그린다(한 번만 그리면 된다). */
export function renderExamples(examples, container, onPick) {
  container.replaceChildren(...examples.map((ex) => exampleButton(ex, onPick)));
}
