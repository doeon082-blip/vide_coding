// render(state): 상태를 보고 대화 영역을 통째로 다시 그린다(조각을 하나씩 고치지 않는다 → 상태와 화면이 어긋나지 않는다).

import { botMessage, followUpRow, suggestionCard, typingBubble, userBubble } from "./components.js";
import { followUps } from "./view-model.js";

/**
 * 대화 목록(thread)을 상태에 맞게 다시 그린다.
 * handlers: onToggleRows(id), onView(id, view), onCopy(text, labelEl), onPick(example)
 * ctx: { examples, canCopy }
 */
export function renderThread(state, thread, handlers, ctx) {
  const items = state.messages.map((m) => (m.role === "user" ? userBubble(m) : botMessage(m, handlers, ctx.canCopy)));
  if (state.phase === "loading") {
    items.push(typingBubble(state.step));
  } else {
    // 마지막이 답이면 이어서 물어볼 만한 질문을 보여 준다(이미 한 질문과 같은 갈래는 뒤로 미룬다).
    const last = state.messages.at(-1);
    if (last?.role === "bot") {
      const asked = state.messages.filter((m) => m.role === "user").map((m) => m.text);
      items.push(followUpRow(followUps(ctx.examples, asked, last.vm.lane), handlers.onPick));
    }
  }
  thread.setAttribute("aria-busy", state.phase === "loading" ? "true" : "false");
  thread.replaceChildren(...items.filter(Boolean));
}

/** 첫 화면의 예시 질문 카드들을 그린다(한 번만 그리면 된다). */
export function renderSuggestions(examples, container, onPick) {
  container.replaceChildren(...examples.map((ex) => suggestionCard(ex, onPick)));
}
