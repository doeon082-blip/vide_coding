// 아래에 붙은 입력창(ChatGPT·Claude·Gemini 같은 대화형): Enter 전송, Shift+Enter 줄바꿈, 글자 수 표시, 높이 맞춤.
// 질문 글자는 이 입력창에만 있고 보낸 뒤 비운다(어디에도 저장하지 않는다).

import { MAX_QUESTION } from "./view-model.js";

/**
 * refs: { form, input, sendButton, counter }, hooks: { isBusy(): boolean, onSubmit(question) }
 * 돌려주는 값: { sync(): 보내기 단추 상태 갱신, focus() }
 */
export function createComposer({ form, input, sendButton, counter }, { isBusy, onSubmit }) {
  function sync() {
    sendButton.disabled = isBusy() || input.value.trim().length === 0;
  }

  /** 글자 수 표시(거의 찼을 때만)와 입력창 높이. field-sizing을 지원하지 않는 브라우저는 줄 수로 높이를 맞춘다. */
  function fit() {
    const left = MAX_QUESTION - input.value.length;
    counter.textContent = left <= 50 ? `${left}자 남음` : "";
    counter.classList.toggle("is-near", left <= 20);
    input.rows = Math.min(6, Math.max(1, input.value.split("\n").length));
    sync();
  }

  function submit() {
    const question = input.value.trim();
    if (!question || isBusy()) return;
    input.value = "";
    fit();
    onSubmit(question);
    input.focus();
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submit();
  });
  // 한글 입력 중(조합 중)의 Enter는 글자를 확정하는 키라서 보내지 않는다.
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
      event.preventDefault();
      submit();
    }
  });
  input.addEventListener("input", fit);
  fit();
  return { sync, focus: () => input.focus() };
}
