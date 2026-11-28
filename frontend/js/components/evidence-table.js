// 화면 조각: '값을 받아 DOM 요소를 돌려주는 함수'. 글자는 el()의 text/자식(= textContent)으로만 넣고, 링크는 view-model이 허용 목록을 통과시킨 href만 받는다.

import { el } from "../lib/dom.js";

/** 근거 표. 처음에는 VISIBLE_ROWS행만, 넘으면 '더 보기' 단추. 휴대폰에서는 가로 스크롤(.table-wrap). */
export function evidenceTable(table, expanded, onToggle) {
  const shown = expanded ? table.rows : table.rows.slice(0, table.visible);
  const grid = el(
    "table",
    {},
    el("caption", { text: `근거 표 (${table.total}행 중 ${shown.length}행)` }),
    el("thead", {}, el("tr", {}, table.columns.map((c) => el("th", { scope: "col", text: c })))),
    el("tbody", {}, shown.map((row) => el("tr", {}, row.map((cell) => el("td", { class: cell.numeric ? "num" : "", text: cell.text }))))),
  );
  const wrap = el("div", { class: "table-wrap", tabindex: "0", role: "region", "aria-label": "근거 표(가로로 밀어 볼 수 있어요)" }, grid);
  if (table.total <= table.visible) return wrap;
  const more = el("button", { type: "button", class: "btn-more", "aria-expanded": expanded ? "true" : "false", text: expanded ? "접기" : `나머지 ${table.total - table.visible}행 더 보기` });
  more.addEventListener("click", onToggle);
  return el("div", {}, wrap, more);
}
