// 시작점: 상태를 만들고, 이벤트를 연결하고, 첫 화면을 그린다.
// 질문 원문은 localStorage 등 어디에도 저장하지 않는다(기획서의 '원문 비저장'). 메모리의 입력창 값만 있다가 사라진다.

import { askServer } from "./api.js";
import { render, renderExamples } from "./render.js";
import { createStore, initialState, setAnswer, setError, setLoading, setStep, toggleRows } from "./state.js";
import { MAX_QUESTION, failureViewModel, toViewModel } from "./view-model.js";
import { dayOf } from "./lib/format.js";

const STEP_DELAYS_MS = [3000, 7000]; // 진행 표시를 0초 → 3초 → 7초에 바꾼다(서버가 실제 단계를 알려 주지 않는다)

const $ = (id) => document.getElementById(id);
const form = $("ask-form");
const input = $("q");
const sendButton = $("send");
const counter = $("counter");
const out = $("out");

// ?offline=1 이면 서버를 부르지 않고 미리 계산한 예시 답만 보여 준다(서비스가 막혔을 때의 예비 화면).
const offline = new URLSearchParams(location.search).get("offline") === "1";
const store = createStore(initialState({ offline }));
let timers = [];

store.subscribe((state) => {
  render(state, out, { onToggleRows: () => store.update(toggleRows) });
  sendButton.disabled = state.phase === "loading";
});

function clearTimers() {
  for (const t of timers) clearTimeout(t);
  timers = [];
}

/** 질문 하나를 처리한다. 질문 중이면 무시(두 번 보내기 방지). */
async function ask(question) {
  if (store.get().phase === "loading") return;
  if (offline) {
    store.update((s) => setError(s, failureViewModel("offline")));
    return;
  }
  store.update(setLoading);
  timers = STEP_DELAYS_MS.map((ms, i) => setTimeout(() => store.update((s) => setStep(s, i + 1)), ms));
  const result = await askServer(question);
  clearTimers();
  if (result.ok) {
    store.update((s) => setAnswer(s, toViewModel(result.data), { kind: "live" }));
  } else {
    store.update((s) => setError(s, failureViewModel(result.kind, result.detail)));
  }
}

/** 예시 단추: 미리 계산한 답이 있으면 서버를 부르지 않고 바로 보여 준다(한도를 아끼고, 서버가 죽어도 시연된다). */
function pickExample(example, generatedAt) {
  input.value = example.question;
  updateCounter();
  if (example.response) {
    store.update((s) => setAnswer(s, toViewModel(example.response), { kind: "example", generatedAt }));
  } else {
    ask(example.question);
  }
}

function updateCounter() {
  const left = MAX_QUESTION - input.value.length;
  counter.textContent = `${left}자 남았어요.`;
  counter.parentElement.classList.toggle("is-near-limit", left <= 20);
}

async function loadExamples() {
  try {
    const res = await fetch("data/examples.json", { cache: "no-store", credentials: "omit" });
    if (!res.ok) return [];
    const data = await res.json();
    const generatedAt = dayOf(data.generated_at);
    const list = Array.isArray(data.examples) ? data.examples : [];
    return list
      .filter((e) => e && typeof e.lane === "string" && typeof e.question === "string")
      .map((e) => ({ ...e, generatedAt }));
  } catch {
    return []; // 예시를 못 읽어도 질문창은 동작한다
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const question = input.value.trim();
  if (question) ask(question);
});
input.addEventListener("input", updateCounter);

$("offline-banner").hidden = !offline;
updateCounter();
render(store.get(), out, { onToggleRows: () => store.update(toggleRows) });
loadExamples().then((examples) => renderExamples(examples, $("examples"), (ex) => pickExample(ex, ex.generatedAt)));
