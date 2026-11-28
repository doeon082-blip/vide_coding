// 화면 조각: '값을 받아 DOM 요소를 돌려주는 함수'. 글자는 el()의 text/자식(= textContent)으로만 넣고, 링크는 view-model이 허용 목록을 통과시킨 href만 받는다.

import { avatar } from "./avatar.js";
import { el } from "../lib/dom.js";

export const STEPS = Object.freeze(["자료 찾는 중", "계산 중", "설명 쓰는 중"]);

/** 답을 만드는 중: 입력 중 점 + 진행 단계('보통 이 순서'라고 밝힌다. 서버가 실제 단계를 알려 주지 않아 시간에 따라 바꾼다). */
export function typingBubble(step) {
  const steps = STEPS.map((name, i) =>
    el("li", { class: i < step ? "is-done" : i === step ? "is-now" : "", text: name, ...(i === step ? { "aria-current": "step" } : {}) }),
  );
  return el(
    "li",
    { class: "msg msg-bot" },
    avatar(),
    el("div", { class: "answer-card", role: "status", "aria-label": "답을 찾는 중" }, el("div", { class: "typing", "aria-hidden": "true" }, el("i"), el("i"), el("i")), el("ol", { class: "progress" }, steps), el("p", { class: "progress-note", text: "보통 이 순서로 진행돼요. 3~10초쯤 걸려요." })),
  );
}
