// 화면 조각: '값을 받아 DOM 요소를 돌려주는 함수'. 글자는 el()의 text/자식(= textContent)으로만 넣고, 링크는 view-model이 허용 목록을 통과시킨 href만 받는다.

import { el } from "../lib/dom.js";

/** 내가 한 질문(오른쪽 말풍선). */
export function userBubble(message) {
  return el("li", { class: "msg msg-user" }, el("p", { class: "bubble-user", text: message.text }));
}
