// 화면 조각: '값을 받아 DOM 요소를 돌려주는 함수'. 글자는 el()의 text/자식(= textContent)으로만 넣고, 링크는 view-model이 허용 목록을 통과시킨 href만 받는다.

import { answerBlock } from "./answer-block.js";
import { avatar } from "./avatar.js";
import { badges } from "./badges.js";
import { copyButton } from "./copy-button.js";
import { documentList } from "./documents.js";
import { evidence } from "./evidence.js";
import { retryButton } from "./retry-button.js";
import { sourceList } from "./sources.js";
import { el } from "../lib/dom.js";
import { laneClass, laneLabel } from "../lib/lane.js";

export const FOOT_LINE = "비공식 서비스 · 답은 틀릴 수 있어요";

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
      answerBlock(message, handlers),
      vm.retryable ? retryButton(() => handlers.onRetry(message.id)) : null,
      badges(vm.badges),
      evidence(message, handlers),
      documentList(vm.documents),
      sourceList(vm.sources),
      el("div", { class: "card-foot" }, el("span", { class: "foot-note", text: vm.notice && vm.notice !== FOOT_LINE ? `${FOOT_LINE} · ${vm.notice}` : FOOT_LINE }), copyButton(vm.answer, canCopy, handlers.onCopy)),
    ),
  );
}
