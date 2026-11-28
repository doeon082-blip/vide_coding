// 화면 조각: '값을 받아 DOM 요소를 돌려주는 함수'. 글자는 el()의 text/자식(= textContent)으로만 넣고, 링크는 view-model이 허용 목록을 통과시킨 href만 받는다.

import { el } from "../lib/dom.js";

/** 답변 복사 단추. 클립보드를 쓸 수 없는 환경(http 등)에서는 만들지 않는다. */
export function copyButton(answer, canCopy, onCopy) {
  if (!canCopy || !answer) return null;
  const button = el("button", { type: "button", class: "btn-copy" }, el("i", { class: "icon icon-copy", "aria-hidden": "true" }), el("span", { text: "답 복사" }));
  button.addEventListener("click", () => onCopy(answer, button.lastElementChild));
  return button;
}
