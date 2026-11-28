// 답 복사. 클립보드 API가 없는 환경(http 등)에서는 복사 단추를 만들지 않는다(components가 canCopy로 판단).

export const canCopyToClipboard = () => typeof navigator.clipboard?.writeText === "function";

/** 답을 복사하고 단추 글자(label)로 결과를 잠깐 알린다. */
export async function copyAnswer(answer, label) {
  try {
    await navigator.clipboard.writeText(answer);
    label.textContent = "복사했어요";
  } catch {
    label.textContent = "복사하지 못했어요";
  }
  setTimeout(() => (label.textContent = "답 복사"), 1600);
}
