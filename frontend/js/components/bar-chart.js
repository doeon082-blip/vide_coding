// 화면 조각: '값을 받아 DOM 요소를 돌려주는 함수'. 글자는 el()의 text/자식(= textContent)으로만 넣고, 링크는 view-model이 허용 목록을 통과시킨 href만 받는다.

import { el, svgEl } from "../lib/dom.js";

/** 막대 그래프: 이름 · 막대 · 값. 막대는 SVG(속성만 사용)라 CSP의 인라인 스타일 제한에 걸리지 않는다. 가장 큰 값은 진하게. */
export function barChart(chart) {
  const rows = chart.bars.map((bar) =>
    el(
      "li",
      { class: bar.top ? "bar-row is-top" : "bar-row" },
      el("span", { class: "bar-label", text: bar.label }),
      svgEl(
        "svg",
        { class: "bar-svg", viewBox: "0 0 100 10", preserveAspectRatio: "none", "aria-hidden": "true" },
        svgEl("rect", { class: "bar-track", x: 0, y: 0, width: 100, height: 10 }),
        svgEl("rect", { class: "bar-fill", x: 0, y: 0, width: Math.max(bar.share * 100, 0.8), height: 10 }), // 0에 가까운 값도 보이도록 최소 폭
      ),
      el("span", { class: "bar-value", text: bar.text }),
    ),
  );
  return el("ul", { class: "bars", "aria-label": `${chart.labelColumn}별 ${chart.valueColumn}` }, rows);
}
