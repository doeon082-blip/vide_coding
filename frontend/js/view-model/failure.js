// 실패(네트워크·시간 초과·서버 오류)를 답변 카드와 같은 모양으로 만든다.

import { FAILURES, STATUS } from "./constants.js";

export function emptyViewModel(fields) {
  return { lane: null, numberNotice: null, badges: [], corrections: [], table: null, documents: [], sources: [], notice: "", ...fields };
}

/** 실패(네트워크·시간 초과·서버 오류)를 카드 모양으로. detail은 서버가 준 일반 문장일 때만 쓴다(길이 제한). */
export function failureViewModel(kind, detail = null) {
  const known = Object.hasOwn(FAILURES, kind) ? kind : "server";
  const useDetail = (known === "blocked" || known === "busy" || known === "server") && typeof detail === "string" && detail.length > 0;
  return emptyViewModel({
    status: known === "blocked" ? "blocked" : "error",
    label: known === "blocked" ? STATUS.blocked.label : "알림",
    tone: known === "blocked" || known === "server" ? "err" : "warn",
    answer: useDetail ? detail.slice(0, 200) : FAILURES[known],
  });
}
