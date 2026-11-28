// 시작점: 상태를 만들고, 조각들(입력창·그리기·스크롤·예시)을 연결하고, 첫 화면을 그린다.
// 질문 원문은 localStorage 등 어디에도 저장하지 않는다(기획서의 '원문 비저장'). 대화 기록은 이 페이지의 메모리에만 있다.

import { askServer } from "./api.js";
import { canCopyToClipboard, copyAnswer } from "./clipboard.js";
import { createComposer } from "./composer.js";
import { loadExamples } from "./examples.js";
import { renderSuggestions, renderThread } from "./render.js";
import { scrollForNew } from "./scroll.js";
import { addAnswer, addQuestion, clearChat, createStore, initialState, setStep, setView, toggleAnswer, toggleRows } from "./state.js";
import { failureViewModel, toViewModel } from "./view-model.js";
import { detectOffline } from "./lib/mode.js";

const STEP_DELAYS_MS = [3000, 7000]; // 진행 표시를 0초 → 3초 → 7초에 바꾼다(서버가 실제 단계를 알려 주지 않는다)

const $ = (id) => document.getElementById(id);
const thread = $("thread");
const hero = $("hero");
const newChat = $("new-chat");

// 예비 모드(?offline=1 또는 서버 없는 정적 호스팅): 서버를 부르지 않고 미리 계산한 예시 답만 보여 준다.
const offline = detectOffline(location.search, location.hostname);
const store = createStore(initialState({ offline }));
const isBusy = () => store.get().phase === "loading";
let examples = [];
let timers = [];
let shown = 0; // 마지막으로 그린 메시지 수(새 메시지가 생겼을 때만 스크롤하려고)

const composer = createComposer(
  { form: $("ask-form"), input: $("q"), sendButton: $("send"), counter: $("counter") },
  { isBusy, onSubmit: (question) => ask(question) },
);

const handlers = {
  onToggleRows: (id) => store.update((s) => toggleRows(s, id)),
  onToggleAnswer: (id) => store.update((s) => toggleAnswer(s, id)),
  onView: (id, view) => store.update((s) => setView(s, id, view)),
  onPick: (example) => pickExample(example),
  onCopy: copyAnswer,
};

store.subscribe((state) => {
  const isEmpty = state.messages.length === 0 && state.phase === "idle";
  hero.hidden = !isEmpty;
  newChat.hidden = isEmpty;
  newChat.disabled = state.phase === "loading";
  renderThread(state, thread, handlers, { examples, canCopy: canCopyToClipboard() });
  composer.sync();
  const grew = state.messages.length > shown || state.phase === "loading";
  shown = state.messages.length;
  if (grew) scrollForNew(state, thread);
});

function clearTimers() {
  for (const t of timers) clearTimeout(t);
  timers = [];
}

/** 질문 하나를 처리한다. 질문 중이면 무시(두 번 보내기 방지). */
async function ask(question) {
  if (isBusy()) return;
  store.update((s) => addQuestion(s, question));
  if (offline) {
    store.update((s) => addAnswer(s, failureViewModel("offline")));
    return;
  }
  timers = STEP_DELAYS_MS.map((ms, i) => setTimeout(() => store.update((s) => setStep(s, i + 1)), ms));
  const result = await askServer(question);
  clearTimers();
  store.update((s) => (result.ok ? addAnswer(s, toViewModel(result.data), { kind: "live" }) : addAnswer(s, failureViewModel(result.kind, result.detail))));
}

/** 예시: 미리 계산한 답이 있으면 서버를 부르지 않고 바로 보여 준다(한도를 아끼고, 서버가 죽어도 시연된다). */
function pickExample(example) {
  if (isBusy()) return;
  if (example.response) {
    store.update((s) => addQuestion(s, example.question));
    store.update((s) => addAnswer(s, toViewModel(example.response), { kind: "example", generatedAt: example.generatedAt }));
  } else {
    ask(example.question);
  }
}

newChat.addEventListener("click", () => {
  store.update(clearChat);
  composer.focus();
});

$("offline-banner").hidden = !offline;
store.update((s) => s); // 첫 화면 그리기(hero 표시)
loadExamples().then((list) => {
  examples = list;
  renderSuggestions(examples, $("suggestions"), handlers.onPick);
});
