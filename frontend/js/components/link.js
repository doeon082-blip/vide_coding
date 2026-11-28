// 화면 조각: '값을 받아 DOM 요소를 돌려주는 함수'. 글자는 el()의 text/자식(= textContent)으로만 넣고, 링크는 view-model이 허용 목록을 통과시킨 href만 받는다.

import { el } from "../lib/dom.js";

/** 링크(허용된 주소) 또는 글자(허용 밖). 새 창으로 열되 opener·referrer를 끊는다. */
export function link(href, label, cls = "") {
  if (href === null || href === undefined) return el("span", { class: cls, text: label });
  return el("a", { class: cls, href, target: "_blank", rel: "noopener noreferrer", text: label });
}
