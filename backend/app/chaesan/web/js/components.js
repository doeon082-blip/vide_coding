// 화면 조각: 모두 '값을 받아 DOM 요소를 돌려주는 함수'다(전역 변수 없음). 값은 view-model.js가 이미 정리해 준 것만 받는다.
// 글자는 el()의 text/자식(= textContent)으로만 들어가고, 링크는 view-model이 허용 목록을 통과시킨 href만 받는다.

import { el } from "./lib/dom.js";

export const STEPS = Object.freeze(["자료 찾는 중", "계산 중", "설명 쓰는 중"]);
export const FOOT_LINE = "비공식 서비스 · 답은 틀릴 수 있어요";

/** 링크(허용된 주소) 또는 글자(허용 밖). 새 창으로 열되 opener·referrer를 끊는다. */
function link(href, label) {
  if (href === null || href === undefined) return el("span", { text: label });
  return el("a", { href, target: "_blank", rel: "noopener noreferrer", text: label });
}

/** 진행 단계 표시. 서버가 실제 단계를 알려 주지 않아 시간에 따라 바꾸므로 '보통 이 순서'라고 밝힌다. */
export function progress(step) {
  const items = STEPS.map((name, i) =>
    el("li", { class: i < step ? "is-done" : i === step ? "is-now" : "", text: name, ...(i === step ? { "aria-current": "step" } : {}) }),
  );
  return el("div", { class: "card" }, el("ol", { class: "progress" }, items), el("p", { class: "progress-note", text: "보통 이 순서로 진행돼요. 3~10초쯤 걸려요." }));
}

/** 배지 줄. 주의 배지는 색뿐 아니라 '주의' 글자도 붙인다. */
export function badges(list) {
  if (list.length === 0) return null;
  return el(
    "ul",
    { class: "badges", "aria-label": "자료 상태" },
    list.map((b) => el("li", { class: b.alert ? "badge is-alert" : "badge", text: b.alert ? `주의 · ${b.text}` : b.text })),
  );
}

/** 근거 표. 처음에는 VISIBLE_ROWS행만, 넘으면 '더 보기' 단추. 휴대폰에서는 가로 스크롤(.table-wrap). */
export function evidenceTable(table, expanded, onToggle) {
  if (table === null) return null;
  const shown = expanded ? table.rows : table.rows.slice(0, table.visible);
  const grid = el(
    "table",
    {},
    el("caption", { text: `근거 표 (${table.total}행 중 ${shown.length}행)` }),
    el("thead", {}, el("tr", {}, table.columns.map((c) => el("th", { scope: "col", text: c })))),
    el("tbody", {}, shown.map((row) => el("tr", {}, row.map((cell) => el("td", { class: cell.numeric ? "num" : "", text: cell.text }))))),
  );
  const parts = [el("div", { class: "table-wrap", tabindex: "0", role: "region", "aria-label": "근거 표(가로로 밀어 볼 수 있어요)" }, grid)];
  if (table.total > table.visible) {
    parts.push(
      el("button", {
        type: "button",
        class: "btn-more",
        "aria-expanded": expanded ? "true" : "false",
        text: expanded ? "접기" : `나머지 ${table.total - table.visible}행 더 보기`,
      }),
    );
    parts[1].addEventListener("click", onToggle);
  }
  return el("div", {}, parts);
}

/** 관련 문서 목록(연혁·소식·FAQ 등). */
export function documentList(docs) {
  if (docs.length === 0) return null;
  return el(
    "div",
    {},
    el("p", { class: "section-title", text: "관련 기록" }),
    el(
      "ul",
      { class: "list" },
      docs.map((d) =>
        el("li", {}, el("span", { class: "meta", text: d.dateText }), link(d.href, d.title), el("span", { class: "meta", text: [d.source, d.bodyMissing ? "본문 없음" : ""].filter(Boolean).join(" · ") })),
      ),
    ),
  );
}

/** 출처 목록: 데이터 이름(번호)·자료 기간·링크. */
export function sourceList(sources) {
  if (sources.length === 0) return null;
  return el(
    "div",
    {},
    el("p", { class: "section-title", text: "출처" }),
    el(
      "ul",
      { class: "list" },
      sources.map((s) => el("li", {}, link(s.href, s.label), s.period ? el("span", { class: "meta", text: `자료 기간 ${s.period}` }) : null)),
    ),
  );
}

/** 답변 카드(성공·모름·되묻기·미연결·실패 모두 같은 모양). */
export function resultCard(vm, { source, expanded, onToggleRows }) {
  return el(
    "article",
    { class: "card" },
    el("p", { class: `kicker tone-${vm.tone}`, text: vm.label }),
    source?.kind === "example" ? el("p", { class: "example-mark", text: source.generatedAt ? `미리 계산한 답 · ${source.generatedAt} 기준` : "미리 계산한 답" }) : null,
    vm.corrections.map((c) => el("p", { class: "correction", text: `✎ ${c}` })),
    vm.numberNotice ? el("p", { class: "number-notice", text: vm.numberNotice }) : null,
    vm.answer !== null ? el("p", { class: "answer", text: vm.answer }) : null,
    badges(vm.badges),
    evidenceTable(vm.table, expanded, onToggleRows),
    documentList(vm.documents),
    sourceList(vm.sources),
    el("p", { class: "card-foot", text: vm.notice && vm.notice !== FOOT_LINE ? `${FOOT_LINE} · ${vm.notice}` : FOOT_LINE }),
  );
}

/** 예시 질문 단추 하나. */
export function exampleButton(example, onPick) {
  const button = el("button", { type: "button", class: "chip-btn" }, el("span", { class: "lane", text: example.lane }), example.question);
  button.addEventListener("click", () => onPick(example));
  return button;
}
