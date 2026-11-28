// 새 메시지가 생겼을 때의 스크롤: 긴 답은 끝이 아니라 처음부터 읽게 하고, 질문·진행 표시는 맨 아래로.

const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");

export function scrollForNew(state, thread) {
  const behavior = reducedMotion.matches ? "auto" : "smooth";
  const last = state.messages.at(-1);
  if (state.phase === "idle" && last?.role === "bot") {
    const cards = thread.querySelectorAll(".msg-bot");
    cards[cards.length - 1]?.scrollIntoView({ block: "start", behavior });
  } else {
    scrollTo({ top: document.documentElement.scrollHeight, behavior });
  }
}
