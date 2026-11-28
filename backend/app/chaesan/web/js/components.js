// 화면 조각: 모두 '값을 받아 DOM 요소를 돌려주는 함수'다(전역 변수 없음). 값은 view-model.js가 이미 정리해 준 것만 받는다.
// 글자는 el()의 text/자식(= textContent)으로만 들어가고, 링크는 view-model이 허용 목록을 통과시킨 href만 받는다.

import { el, svgEl } from "./lib/dom.js";
import { laneClass, laneKeyByLabel, laneLabel } from "./lib/lane.js";

export const STEPS = Object.freeze(["자료 찾는 중", "계산 중", "설명 쓰는 중"]);
export const FOOT_LINE = "비공식 서비스 · 답은 틀릴 수 있어요";

/** 링크(허용된 주소) 또는 글자(허용 밖). 새 창으로 열되 opener·referrer를 끊는다. */
function link(href, label) {
  if (href === null || href === undefined) return el("span", { text: label });
  return el("a", { href, target: "_blank", rel: "noopener noreferrer", text: label });
}

const avatar = () => el("img", { class: "avatar", src: "img/mark.svg", alt: "", width: "32", height: "32" });

// ------------------------------------------------------------------ 첫 화면의 예시 카드, 이어서 묻기

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

// ------------------------------------------------------------------ 말풍선

export function userBubble(message) {
  return el("li", { class: "msg msg-user" }, el("p", { class: "bubble-user", text: message.text }));
}

/** 답을 만드는 중: 입력 중 점 + 진행 단계('보통 이 순서'라고 밝힌다. 서버가 실제 단계를 알려 주지 않아 시간에 따라 바꾼다). */
export function typingBubble(step) {
  const steps = STEPS.map((name, i) =>
    el("li", { class: i < step ? "is-done" : i === step ? "is-now" : "", text: name, ...(i === step ? { "aria-current": "step" } : {}) }),
  );
  return el(
    "li",
    { class: "msg msg-bot" },
    avatar(),
    el("div", { class: "answer-card", role: "status", "aria-label": "답을 찾는 중" }, el("div", { class: "typing", "aria-hidden": "true" }, el("i"), el("i"), el("i")), el("ol", { class: "progress" }, steps), el("p", { class: "progress-note", text: "보통 이 순서로 진행돼요. 3~10초쯤 걸려요." })),
  );
}

// ------------------------------------------------------------------ 답변 카드 조각

/** 배지 줄. 주의 배지는 색뿐 아니라 '주의' 글자도 붙인다. */
export function badges(list) {
  if (list.length === 0) return null;
  return el("ul", { class: "badges", "aria-label": "자료 상태" }, list.map((b) => el("li", { class: b.alert ? "badge is-alert" : "badge", text: b.alert ? `주의 · ${b.text}` : b.text })));
}

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

/** 관련 문서 목록(연혁·소식·FAQ 등). */
export function documentList(docs) {
  if (docs.length === 0) return null;
  return el(
    "div",
    {},
    el("p", { class: "section-title", text: "관련 기록" }),
    el("ul", { class: "list" }, docs.map((d) => el("li", {}, el("span", { class: "meta", text: d.dateText }), link(d.href, d.title), el("span", { class: "meta", text: [d.source, d.bodyMissing ? "본문 없음" : ""].filter(Boolean).join(" · ") })))),
  );
}

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

/** 답변 복사 단추. 클립보드를 쓸 수 없는 환경(http 등)에서는 만들지 않는다. */
function copyButton(answer, canCopy, onCopy) {
  if (!canCopy || !answer) return null;
  const button = el("button", { type: "button", class: "btn-copy" }, el("i", { class: "icon icon-copy", "aria-hidden": "true" }), el("span", { text: "답 복사" }));
  button.addEventListener("click", () => onCopy(answer, button.lastElementChild));
  return button;
}

/** 답변 카드(성공·모름·되묻기·미연결·실패 모두 같은 모양). 갈래별 색과 아이콘이 입혀진다. */
export function botMessage(message, handlers, canCopy) {
  const { vm, source } = message;
  const lane = laneClass(vm.lane);
  const showStatus = vm.status !== "answered";
  return el(
    "li",
    { class: `msg msg-bot ${lane}` },
    avatar(),
    el(
      "article",
      { class: "answer-card" },
      el("div", { class: "card-head" }, el("span", { class: "lane-chip" }, el("i", { class: "lane-icon", "aria-hidden": "true" }), laneLabel(vm.lane)), showStatus ? el("span", { class: `status-chip tone-${vm.tone}`, text: vm.label }) : null),
      source?.kind === "example" ? el("p", { class: "example-mark", text: source.generatedAt ? `미리 계산한 답 · ${source.generatedAt} 기준` : "미리 계산한 답" }) : null,
      vm.corrections.map((c) => el("p", { class: "correction", text: `✎ ${c}` })),
      vm.numberNotice ? el("p", { class: "number-notice", text: vm.numberNotice }) : null,
      vm.answer !== null ? el("p", { class: "answer", text: vm.answer }) : null,
      badges(vm.badges),
      evidence(message, handlers),
      documentList(vm.documents),
      sourceList(vm.sources),
      el("div", { class: "card-foot" }, el("span", { class: "foot-note", text: vm.notice && vm.notice !== FOOT_LINE ? `${FOOT_LINE} · ${vm.notice}` : FOOT_LINE }), copyButton(vm.answer, canCopy, handlers.onCopy)),
    ),
  );
}
