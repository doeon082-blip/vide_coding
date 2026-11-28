// 화면 조각: '값을 받아 DOM 요소를 돌려주는 함수'. 글자는 el()의 text/자식(= textContent)으로만 넣고, 링크는 view-model이 허용 목록을 통과시킨 href만 받는다.

import { el } from "../lib/dom.js";
import { laneClass, laneKeyByLabel } from "../lib/lane.js";

/** 첫 화면의 예시 질문 카드: 갈래 색·아이콘·갈래 이름·질문. */
export function suggestionCard(example, onPick) {
  const key = laneKeyByLabel(example.lane);
  const card = el(
    "button",
    { type: "button", class: `suggest ${laneClass(key)}` },
    el("span", { class: "suggest-icon" }, el("i", { class: "lane-icon", "aria-hidden": "true" })),
    el("span", { class: "suggest-lane", text: example.lane }),
    el("span", { class: "suggest-q", text: example.question }),
  );
  card.addEventListener("click", () => onPick(example));
  return card;
}

/** 답 아래의 '이어서 물어볼 만한 질문' 칩. */
export function followUpRow(examples, onPick) {
  if (examples.length === 0) return null;
  return el(
    "li",
    { class: "followups", "aria-label": "이어서 물어볼 만한 질문" },
    examples.map((ex) => {
      const chip = el("button", { type: "button", class: `follow-chip ${laneClass(laneKeyByLabel(ex.lane))}` }, el("i", { class: "lane-icon", "aria-hidden": "true" }), ex.question);
      chip.addEventListener("click", () => onPick(ex));
      return chip;
    }),
  );
}
