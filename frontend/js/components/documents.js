// 화면 조각: '값을 받아 DOM 요소를 돌려주는 함수'. 글자는 el()의 text/자식(= textContent)으로만 넣고, 링크는 view-model이 허용 목록을 통과시킨 href만 받는다.

import { link } from "./link.js";
import { el } from "../lib/dom.js";

/** 관련 문서 목록(연혁·소식·FAQ 등). */
export function documentList(docs) {
  if (docs.length === 0) return null;
  return el(
    "div",
    {},
    el("p", { class: "section-title", text: "관련 기록" }),
    el("ul", { class: "list" }, docs.map((d) => el("li", {}, el("span", { class: "meta", text: d.dateText }), link(d.href, d.title, "doc-title"), el("span", { class: "meta", text: [d.source, d.bodyMissing ? "본문 없음" : ""].filter(Boolean).join(" · ") })))),
  );
}
