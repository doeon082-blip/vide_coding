// 서버 응답(JSON) → 화면에 쓸 값. DOM을 쓰지 않는 순수 함수라서 브라우저 없이 node --test로 시험한다.
// 원칙: 서버가 준 값을 고치거나 계산하지 않는다. 다만 ① 숫자 미확인이면 한 줄 답을 숨기고(방어 한 겹 더),
// ② 링크는 허용 목록을 통과한 것만 링크로 만들고, ③ 막대 그래프의 길이(값/최댓값)만 '표시용'으로 계산한다.

import { formatCell, isNumeric } from "./lib/format.js";
import { laneKeyByLabel, laneKeyOf } from "./lib/lane.js";
import { safeUrl } from "./lib/safe-url.js";

export const MAX_QUESTION = 200; // 서버 core.config.MAX_QUESTION_LEN과 같아야 한다(테스트가 비교)
export const VISIBLE_ROWS = 20;
export const CHART_MIN_ROWS = 3;
export const CHART_MAX_ROWS = 24;
const MAX_COLUMNS = 12;
const MAX_DOCS = 20;

// 서버 status(engine.Status)와 1:1. tone은 글자와 함께 색을 고르는 데만 쓴다.
const STATUS = {
  answered: { label: "답변", tone: "ok" },
  unknown: { label: "근거를 찾지 못했어요", tone: "warn" },
  clarify: { label: "확인이 필요해요", tone: "warn" },
  planned: { label: "아직 연결하지 않은 자료예요", tone: "warn" },
  blocked: { label: "처리할 수 없는 질문이에요", tone: "err" },
  error: { label: "오류", tone: "err" },
};
const ALERT_BADGE = /갱신 안 됨|확인하세요|다를 수|본문 없음|기간 정보 없음/;
export const NUMBER_NOTICE = "숫자를 확인하지 못해 근거 표만 보여 드려요.";

const FAILURES = {
  timeout: "답이 늦어지고 있어요. 다시 시도해 주세요.",
  network: "서버에 연결하지 못했어요. 인터넷 연결을 확인하고 다시 시도해 주세요.",
  rate: "질문이 너무 많아요. 잠시 후 다시 물어봐 주세요. 예시 질문은 계속 볼 수 있어요.",
  invalid: `질문은 1자 이상 ${MAX_QUESTION}자 이하로 써 주세요.`,
  blocked: "처리할 수 없는 질문이에요. 다른 말로 물어봐 주세요.",
  busy: "지금은 질문이 많아요. 잠시 후 다시 물어봐 주세요.",
  server: "지금은 답을 만들 수 없어요. 잠시 후 다시 시도해 주세요.",
  offline: "서버 없이 보는 예비 화면이라 직접 질문할 수 없어요. 예시 질문을 눌러 보세요.",
};

const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const text = (v) => (typeof v === "string" ? v : v === null || v === undefined ? "" : String(v));

function emptyViewModel(fields) {
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

/**
 * 막대 그래프를 그릴 수 있으면 { labelColumn, valueColumn, bars }, 아니면 null.
 * 조건: 3~24행, 열 2개 이상, 모든 행이 숫자(0 이상)인 열이 있음. 값 열은 그런 열 중 마지막, 이름 칸은 나머지 열(최대 2개)을 합친 것.
 * 길이(share)는 값/최댓값으로 '표시용'으로만 계산한다. 서버의 값은 바꾸지 않고, 글자(text)는 표와 같은 서식이다.
 */
export function chartOf(columns, raw, cells) {
  const n = raw.length;
  if (n < CHART_MIN_ROWS || n > CHART_MAX_ROWS || columns.length < 2) return null;
  const numeric = columns.map((_, j) => j).filter((j) => raw.every((row) => isNumeric(row[j]) && row[j] >= 0));
  if (numeric.length === 0) return null;
  const valueIndex = numeric[numeric.length - 1];
  const labelIndexes = columns.map((_, j) => j).filter((j) => j !== valueIndex).slice(0, 2);
  const values = raw.map((row) => row[valueIndex]);
  const max = Math.max(...values);
  if (!(max > 0)) return null;
  return {
    labelColumn: labelIndexes.map((j) => columns[j]).join(" · "),
    valueColumn: columns[valueIndex],
    bars: raw.map((row, i) => ({
      label: labelIndexes.map((j) => cells[i][j].text).join(" · "),
      text: cells[i][valueIndex].text,
      share: Math.round((row[valueIndex] / max) * 10000) / 10000,
      top: row[valueIndex] === max,
    })),
  };
}

function tableOf(rows) {
  const objects = Array.isArray(rows) ? rows.filter(isObject) : [];
  if (objects.length === 0) return null;
  const columns = [];
  for (const row of objects) {
    for (const key of Object.keys(row)) {
      if (!columns.includes(key) && columns.length < MAX_COLUMNS) columns.push(key);
    }
  }
  const raw = objects.map((row) => columns.map((c) => row[c]));
  const cells = raw.map((r) => r.map((v, j) => ({ text: formatCell(columns[j], v), numeric: isNumeric(v) })));
  return { columns, rows: cells, total: cells.length, visible: Math.min(cells.length, VISIBLE_ROWS), chart: chartOf(columns, raw, cells) };
}

function documentsOf(docs) {
  if (!Array.isArray(docs)) return [];
  return docs
    .filter(isObject)
    .slice(0, MAX_DOCS)
    .map((d) => ({
      dateText: text(d.date) || "날짜 없음",
      title: text(d.title) || "(제목 없음)",
      source: text(d.source),
      href: safeUrl(d.url), // 허용 목록 밖이면 null → 글자로만 보인다
      bodyMissing: d.body_available === false,
    }));
}

function sourcesOf(sources) {
  if (!Array.isArray(sources)) return [];
  return sources.filter(isObject).map((s) => ({
    label: s.id ? `${text(s.name)}(${text(s.id)})` : text(s.name),
    period: text(s.period),
    href: safeUrl(s.url),
  }));
}

/** 서버 응답 → 화면 값. 모양이 틀리면 일반 오류 카드. */
export function toViewModel(data) {
  if (!isObject(data) || typeof data.answer !== "string") return failureViewModel("server");
  const status = Object.hasOwn(STATUS, data.status) ? data.status : "error";
  const unsupported = Array.isArray(data.unsupported_numbers) && data.unsupported_numbers.length > 0;
  return emptyViewModel({
    status,
    label: STATUS[status].label,
    tone: STATUS[status].tone,
    lane: isObject(data.meta) ? laneKeyOf(data.meta.intent) : null, // 서버가 계획 단계에서 정한 질문 갈래
    // 서버가 이미 숫자를 뺐더라도, 확인 못 한 숫자가 있다고 표시되면 화면에서도 한 줄 답을 보이지 않는다.
    answer: unsupported ? null : data.answer,
    numberNotice: unsupported ? NUMBER_NOTICE : null,
    badges: (Array.isArray(data.badges) ? data.badges : [])
      .filter((b) => typeof b === "string" && b.length > 0)
      .map((b) => ({ text: b, alert: ALERT_BADGE.test(b) })),
    corrections: (Array.isArray(data.corrections) ? data.corrections : []).filter((c) => typeof c === "string"),
    table: tableOf(data.evidence_rows),
    documents: documentsOf(data.documents),
    sources: sourcesOf(data.sources),
    notice: text(data.notice),
  });
}

export const LONG_ANSWER = 140;

/** 근거 표·그래프가 따로 있는데 한 줄 답이 숫자 나열처럼 길면 처음에는 줄여 보인다('전체 보기'로 펼침). */
export const isLongAnswer = (vm) => vm.answer !== null && vm.table !== null && vm.answer.length > LONG_ANSWER;

/** 처음 보여 줄 근거 보기: 그래프를 그릴 수 있으면 그래프, 아니면 표. */
export const defaultView = (vm) => (vm.table?.chart ? "chart" : "table");

/**
 * 답 아래에 보여 줄 '이어서 물어볼 만한 질문'(최대 limit개). 이미 한 질문은 빼고, 다른 갈래를 먼저 고른다(다양하게).
 * examples: [{ lane: "데이터", question: "..." }], asked: 이미 물은 질문 글자들.
 */
export function followUps(examples, asked, currentLane, limit = 3) {
  const done = new Set(asked);
  const fresh = examples.filter((e) => !done.has(e.question));
  const out = [];
  const seen = new Set([currentLane]);
  for (const ex of fresh) {
    const key = laneKeyByLabel(ex.lane);
    if (!seen.has(key) && out.length < limit) {
      out.push(ex);
      seen.add(key);
    }
  }
  for (const ex of fresh) if (out.length < limit && !out.includes(ex)) out.push(ex);
  return out;
}
