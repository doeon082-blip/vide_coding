// 화면 조각: '값을 받아 DOM 요소를 돌려주는 함수'. 글자는 el()의 text/자식(= textContent)으로만 넣고, 링크는 view-model이 허용 목록을 통과시킨 href만 받는다.

import { el } from "../lib/dom.js";
import { isLongAnswer } from "../view-model.js";

/** 한 줄 답. 근거 표·그래프가 따로 있는데 답이 길면(숫자 나열) 3줄까지만 보이고 '전체 보기'로 펼친다. */
export function answerBlock(message, handlers) {
  const { vm } = message;
  if (vm.answer === null) return null;
  const clamp = isLongAnswer(vm) && !message.answerOpen;
  const paragraph = el("p", { class: clamp ? "answer is-clamped" : "answer", text: vm.answer });
  if (!isLongAnswer(vm)) return paragraph;
  const toggle = el("button", { type: "button", class: "btn-link", "aria-expanded": clamp ? "false" : "true", text: clamp ? "답 전체 보기" : "답 줄이기" });
  toggle.addEventListener("click", () => handlers.onToggleAnswer(message.id));
  return el("div", { class: "answer-block" }, paragraph, toggle);
}
