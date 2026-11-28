// 실패했을 때 같은 질문을 다시 보내는 단추. 잠깐의 문제(연결·시간 초과·혼잡·서버)에만 보인다(view-model의 retryable).

import { el } from "../lib/dom.js";

export function retryButton(onRetry) {
  const button = el("button", { type: "button", class: "btn-retry", text: "다시 시도" });
  button.addEventListener("click", onRetry);
  return button;
}
