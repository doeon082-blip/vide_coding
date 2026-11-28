// 서버 응답 → 화면 값(답변 카드 하나). 모양이 틀리면 일반 오류 카드.

import { ALERT_BADGE, LONG_ANSWER, NUMBER_NOTICE, STATUS } from "./constants.js";
import { documentsOf } from "./documents.js";
import { emptyViewModel, failureViewModel } from "./failure.js";
import { isObject, text } from "./guards.js";
import { sourcesOf } from "./sources.js";
import { tableOf } from "./table.js";
import { laneKeyOf } from "../lib/lane.js";

/** 서버 응답 → 화면 값. 모양이 틀리면 일반 오류 카드. */
export function toViewModel(data) {
  if (!isObject(data) || typeof data.answer !== "string") return failureViewModel("server");
  const status = Object.hasOwn(STATUS, data.status) ? data.status : "error";
  const unsupported = Array.isArray(data.unsupported_numbers) && data.unsupported_numbers.length > 0;
  return emptyViewModel({
    status,
    label: STATUS[status].label,
    tone: STATUS[status].tone,
    lane: isObject(data.meta) ? laneKeyOf(data.meta.intent) : null, // 서버가 계획 단계에서 정한 질문 갈래
    // 서버가 이미 숫자를 뺐더라도, 확인 못 한 숫자가 있다고 표시되면 화면에서도 한 줄 답을 보이지 않는다.
    answer: unsupported ? null : data.answer,
    numberNotice: unsupported ? NUMBER_NOTICE : null,
    badges: (Array.isArray(data.badges) ? data.badges : [])
      .filter((b) => typeof b === "string" && b.length > 0)
      .map((b) => ({ text: b, alert: ALERT_BADGE.test(b) })),
    corrections: (Array.isArray(data.corrections) ? data.corrections : []).filter((c) => typeof c === "string"),
    table: tableOf(data.evidence_rows),
    documents: documentsOf(data.documents),
    sources: sourcesOf(data.sources),
    notice: text(data.notice),
  });
}

/** 근거 표·그래프가 따로 있는데 한 줄 답이 숫자 나열처럼 길면 처음에는 줄여 보인다('전체 보기'로 펼침). */
export const isLongAnswer = (vm) => vm.answer !== null && vm.table !== null && vm.answer.length > LONG_ANSWER;

/** 처음 보여 줄 근거 보기: 그래프를 그릴 수 있으면 그래프, 아니면 표. */
export const defaultView = (vm) => (vm.table?.chart ? "chart" : "table");
