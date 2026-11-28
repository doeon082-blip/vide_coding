// 화면 조각: '값을 받아 DOM 요소를 돌려주는 함수'. 글자는 el()의 text/자식(= textContent)으로만 넣고, 링크는 view-model이 허용 목록을 통과시킨 href만 받는다.

import { barChart } from "./bar-chart.js";
import { evidenceTable } from "./evidence-table.js";
import { el } from "../lib/dom.js";

/** 근거 영역: 그래프를 그릴 수 있으면 [그래프|표] 전환, 아니면 표만. */
export function evidence(message, handlers) {
  const table = message.vm.table;
  if (table === null) return null;
  if (!table.chart) return evidenceTable(table, message.expanded, () => handlers.onToggleRows(message.id));
  const tab = (view, label) => {
    const b = el("button", { type: "button", class: "tab", role: "tab", "aria-selected": message.view === view ? "true" : "false", text: label });
    b.addEventListener("click", () => handlers.onView(message.id, view));
    return b;
  };
  return el(
    "div",
    { class: "viz" },
    el("div", { class: "viz-head" }, el("span", { class: "viz-caption", text: message.view === "chart" ? `${table.chart.labelColumn}별 ${table.chart.valueColumn}` : "근거 표" }), el("div", { class: "tabs", role: "tablist", "aria-label": "근거 보기 방식" }, tab("chart", "그래프"), tab("table", "표"))),
    message.view === "chart" ? barChart(table.chart) : evidenceTable(table, message.expanded, () => handlers.onToggleRows(message.id)),
  );
}
