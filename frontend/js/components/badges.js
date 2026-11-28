// 화면 조각: '값을 받아 DOM 요소를 돌려주는 함수'. 글자는 el()의 text/자식(= textContent)으로만 넣고, 링크는 view-model이 허용 목록을 통과시킨 href만 받는다.

import { el } from "../lib/dom.js";

/** 배지 줄. 주의 배지는 색뿐 아니라 '주의' 글자도 붙인다. */
export function badges(list) {
  if (list.length === 0) return null;
  return el("ul", { class: "badges", "aria-label": "자료 상태" }, list.map((b) => el("li", { class: b.alert ? "badge is-alert" : "badge", text: b.alert ? `주의 · ${b.text}` : b.text })));
}
