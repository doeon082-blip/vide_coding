// 화면 조각: '값을 받아 DOM 요소를 돌려주는 함수'. 글자는 el()의 text/자식(= textContent)으로만 넣고, 링크는 view-model이 허용 목록을 통과시킨 href만 받는다.

import { link } from "./link.js";
import { el } from "../lib/dom.js";

/** 출처 목록: 데이터 이름(번호)·자료 기간·링크. */
export function sourceList(sources) {
  if (sources.length === 0) return null;
  return el(
    "div",
    {},
    el("p", { class: "section-title", text: "출처" }),
    el("ul", { class: "list" }, sources.map((s) => el("li", {}, link(s.href, s.label), s.period ? el("span", { class: "meta", text: `자료 기간 ${s.period}` }) : null))),
  );
}
