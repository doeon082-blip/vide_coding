// 실패(네트워크·시간 초과·서버 오류)를 답변 카드와 같은 모양으로 만든다.

import { FAILURES, STATUS } from "./constants.js";

const RETRYABLE = new Set(["timeout", "network", "busy", "server"]);

export function emptyViewModel(fields) {
  return { lane: null, retryable: false, numberNotice: null, badges: [], corrections: [], table: null, documents: [], sources: [], notice: "", ...fields };
}

/** 실패(네트워크·시간 초과·서버 오류)를 카드 모양으로. detail은 서버가 준 일반 문장일 때만 쓴다(길이 제한). */
export function failureViewModel(kind, detail = null) {
  const known = Object.hasOwn(FAILURES, kind) ? kind : "server";
  const useDetail = (known === "blocked" || known === "busy" || known === "server" || known === "rate") && typeof detail === "string" && detail.length > 0;
  return emptyViewModel({
    status: known === "blocked" ? "blocked" : "error",
    label: known === "blocked" ? STATUS.blocked.label : "알림",
    tone: known === "blocked" || known === "server" ? "err" : "warn",
    answer: useDetail ? detail.slice(0, 200) : FAILURES[known],
    retryable: RETRYABLE.has(known), // 잠깐의 문제(시간 초과·연결·혼잡·서버)만 다시 시도를 권한다. 차단·길이·한도는 같은 질문을 다시 보내도 같다.
  });
}
