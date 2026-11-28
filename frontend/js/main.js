// 시작점: 상태를 만들고, 이벤트를 연결하고, 첫 화면을 그린다.
// 질문 원문은 localStorage 등 어디에도 저장하지 않는다(기획서의 '원문 비저장'). 대화 기록은 이 페이지의 메모리에만 있다.

import { askServer } from "./api.js";
import { renderSuggestions, renderThread } from "./render.js";
import { addAnswer, addQuestion, clearChat, createStore, initialState, setStep, setView, toggleAnswer, toggleRows } from "./state.js";
import { MAX_QUESTION, failureViewModel, toViewModel } from "./view-model.js";
import { dayOf } from "./lib/format.js";
import { detectOffline } from "./lib/mode.js";

const STEP_DELAYS_MS = [3000, 7000]; // 진행 표시를 0초 → 3초 → 7초에 바꾼다(서버가 실제 단계를 알려 주지 않는다)

const $ = (id) => document.getElementById(id);
const form = $("ask-form");
const input = $("q");
const sendButton = $("send");
const counter = $("counter");
const thread = $("thread");
const hero = $("hero");
const newChat = $("new-chat");

// 예비 모드(?offline=1 또는 서버 없는 정적 호스팅): 서버를 부르지 않고 미리 계산한 예시 답만 보여 준다.
const offline = detectOffline(location.search, location.hostname);
const store = createStore(initialState({ offline }));
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
const canCopy = typeof navigator.clipboard?.writeText === "function";
let examples = [];
let timers = [];
let shown = 0; // 마지막으로 그린 메시지 수(새 메시지가 생겼을 때만 스크롤하려고)

const handlers = {
  onToggleRows: (id) => store.update((s) => toggleRows(s, id)),
  onToggleAnswer: (id) => store.update((s) => toggleAnswer(s, id)),
  onView: (id, view) => store.update((s) => setView(s, id, view)),
  onPick: (example) => pickExample(example),
  async onCopy(answer, label) {
    try {
      await navigator.clipboard.writeText(answer);
      label.textContent = "복사했어요";
    } catch {
      label.textContent = "복사하지 못했어요";
    }
    setTimeout(() => (label.textContent = "답 복사"), 1600);
  },
};

function scrollForNew(state) {
  const behavior = reducedMotion.matches ? "auto" : "smooth";
  const last = state.messages.at(-1);
  if (state.phase === "idle" && last?.role === "bot") {
    // 긴 답은 끝이 아니라 처음부터 읽게 한다
    const cards = thread.querySelectorAll(".msg-bot");
    cards[cards.length - 1]?.scrollIntoView({ block: "start", behavior });
  } else {
    scrollTo({ top: document.documentElement.scrollHeight, behavior });
  }
}

store.subscribe((state) => {
  const isEmpty = state.messages.length === 0 && state.phase === "idle";
  hero.hidden = !isEmpty;
  newChat.hidden = isEmpty;
  newChat.disabled = state.phase === "loading";
  renderThread(state, thread, handlers, { examples, canCopy });
  syncSend();
  const grew = state.messages.length > shown || state.phase === "loading";
  shown = state.messages.length;
  if (grew) scrollForNew(state);
});

function clearTimers() {
  for (const t of timers) clearTimeout(t);
  timers = [];
}

/** 질문 하나를 처리한다. 질문 중이면 무시(두 번 보내기 방지). */
async function ask(question) {
  if (store.get().phase === "loading") return;
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
  if (store.get().phase === "loading") return;
  if (example.response) {
    store.update((s) => addQuestion(s, example.question));
    store.update((s) => addAnswer(s, toViewModel(example.response), { kind: "example", generatedAt: example.generatedAt }));
  } else {
    ask(example.question);
  }
}

function submit() {
  const question = input.value.trim();
  if (!question || store.get().phase === "loading") return;
  input.value = "";
  fitInput();
  ask(question);
  input.focus();
}

function syncSend() {
  sendButton.disabled = store.get().phase === "loading" || input.value.trim().length === 0;
}

/** 글자 수 표시(거의 찼을 때만)와 입력창 높이. field-sizing을 지원하지 않는 브라우저는 줄 수로 높이를 맞춘다. */
function fitInput() {
  const left = MAX_QUESTION - input.value.length;
  counter.textContent = left <= 50 ? `${left}자 남음` : "";
  counter.classList.toggle("is-near", left <= 20);
  input.rows = Math.min(6, Math.max(1, input.value.split("\n").length));
  syncSend();
}

async function loadExamples() {
  try {
    const res = await fetch("data/examples.json", { cache: "no-store", credentials: "omit" });
    if (!res.ok) return [];
    const data = await res.json();
    const generatedAt = dayOf(data.generated_at);
    const list = Array.isArray(data.examples) ? data.examples : [];
    return list.filter((e) => e && typeof e.lane === "string" && typeof e.question === "string").map((e) => ({ ...e, generatedAt }));
  } catch {
    return []; // 예시를 못 읽어도 질문창은 동작한다
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  submit();
});
// Enter로 보내기, Shift+Enter는 줄바꿈. 한글 입력 중(조합 중)의 Enter는 글자를 확정하는 키라서 보내지 않는다.
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
    event.preventDefault();
    submit();
  }
});
input.addEventListener("input", fitInput);
newChat.addEventListener("click", () => {
  store.update(clearChat);
  input.focus();
});

$("offline-banner").hidden = !offline;
fitInput();
store.update((s) => s); // 첫 화면 그리기(hero 표시)
loadExamples().then((list) => {
  examples = list;
  renderSuggestions(examples, $("suggestions"), handlers.onPick);
});
