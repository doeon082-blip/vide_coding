// 화면 값 정리 시험: 서버 응답을 그대로 보여 주되, 숫자 미확인·위험 링크·큰 표를 규칙대로 처리하는지.
import assert from "node:assert/strict";
import test from "node:test";
import { MAX_QUESTION, NUMBER_NOTICE, VISIBLE_ROWS, failureViewModel, toViewModel } from "../js/view-model.js";

const base = { status: "answered", answer: "올림픽공원 주차는 14시에 가장 많아요.", evidence_rows: [], documents: [], sources: [], badges: [], corrections: [], unsupported_numbers: [], notice: "" };

test("정상 응답: 한 줄 답·배지·출처가 그대로 나온다", () => {
  const vm = toViewModel({
    ...base,
    badges: ["2024년 7월 자료", "1년 넘게 갱신 안 됨"],
    sources: [{ name: "주차 현황", id: "15133891", period: "2024-07", url: "https://www.data.go.kr/data/15133891/fileData.do" }],
    evidence_rows: [{ hour: 14, users: 215528 }],
  });
  assert.equal(vm.answer, base.answer);
  assert.deepEqual(vm.badges.map((b) => b.alert), [false, true]);
  assert.equal(vm.sources[0].label, "주차 현황(15133891)");
  assert.equal(vm.sources[0].href, "https://www.data.go.kr/data/15133891/fileData.do");
  assert.deepEqual(vm.table.rows[0].map((c) => c.text), ["14", "215,528"]);
});

test("숫자 미확인이 있으면 한 줄 답을 숨기고 근거 표만 보인다", () => {
  const vm = toViewModel({ ...base, unsupported_numbers: ["999"], evidence_rows: [{ a: 1 }] });
  assert.equal(vm.answer, null);
  assert.equal(vm.numberNotice, NUMBER_NOTICE);
  assert.equal(vm.table.total, 1);
});

test("허용 밖·위험 링크는 링크가 되지 않고 글자만 남는다", () => {
  const vm = toViewModel({
    ...base,
    documents: [
      { date: "2024-01-01", title: "공지", url: "javascript:alert(1)", source: "누리집", body_available: true },
      { date: "", title: "외부", url: "https://evil.example/", source: "누리집", body_available: false },
      { date: "2024-02-01", title: "정상", url: "https://www.ksponco.or.kr/olympicpark/board.es?mid=a20601000", source: "누리집", body_available: true },
    ],
    sources: [{ name: "나쁜 출처", id: "1", period: "", url: "http://www.data.go.kr/" }],
  });
  assert.deepEqual(vm.documents.map((d) => d.href !== null), [false, false, true]);
  assert.equal(vm.documents[1].dateText, "날짜 없음");
  assert.equal(vm.documents[1].bodyMissing, true);
  assert.equal(vm.sources[0].href, null);
});

test("<script>가 든 문자열도 그대로 글자로 전달된다(걸러내지도 해석하지도 않는다)", () => {
  const vm = toViewModel({ ...base, answer: "<script>alert(1)</script>", evidence_rows: [{ x: "<img src=x onerror=alert(1)>" }] });
  assert.equal(vm.answer, "<script>alert(1)</script>");
  assert.equal(vm.table.rows[0][0].text, "<img src=x onerror=alert(1)>");
});

test("근거 표는 처음 20행만 보이고 전체 행 수를 알려 준다", () => {
  const rows = Array.from({ length: 21 }, (_, i) => ({ n: i }));
  const t = toViewModel({ ...base, evidence_rows: rows }).table;
  assert.equal(t.visible, VISIBLE_ROWS);
  assert.equal(t.total, 21);
  assert.equal(toViewModel({ ...base, evidence_rows: rows.slice(0, 20) }).table.visible, 20);
});

test("열은 모든 행의 열 이름 합집합(최대 12개), 빈 행·객체 아닌 행은 버린다", () => {
  const t = toViewModel({ ...base, evidence_rows: [{ a: 1 }, { a: 2, b: 3 }, null, 5, [1]] }).table;
  assert.deepEqual(t.columns, ["a", "b"]);
  assert.equal(t.total, 2);
  const wide = toViewModel({ ...base, evidence_rows: [Object.fromEntries(Array.from({ length: 30 }, (_, i) => [`c${i}`, i]))] }).table;
  assert.equal(wide.columns.length, 12);
});

test("서버의 모든 status를 표시하고, 모르는 값은 오류로", () => {
  for (const status of ["answered", "unknown", "clarify", "planned", "blocked", "error"]) {
    assert.equal(toViewModel({ ...base, status }).status, status);
  }
  assert.equal(toViewModel({ ...base, status: "weird" }).status, "error");
});

test("응답 모양이 틀리면 일반 오류 카드(내부 내용을 보이지 않음)", () => {
  for (const bad of [null, undefined, "str", 5, [], {}, { answer: 5 }]) {
    const vm = toViewModel(bad);
    assert.equal(vm.status, "error");
    assert.ok(vm.answer.includes("답을 만들 수 없어요"));
  }
});

test("badges·corrections가 배열이 아니거나 이상한 값이어도 죽지 않는다", () => {
  const vm = toViewModel({ ...base, badges: "x", corrections: { a: 1 }, documents: "x", sources: 3, unsupported_numbers: "x" });
  assert.deepEqual([vm.badges, vm.corrections, vm.documents, vm.sources], [[], [], [], []]);
  assert.equal(vm.answer, base.answer);
  assert.deepEqual(toViewModel({ ...base, badges: ["ok", 5, ""] }).badges.map((b) => b.text), ["ok"]);
});

test("실패 카드: 종류별 문구, 서버 문장은 차단·혼잡·서버 오류에서만 쓰고 길이를 자른다", () => {
  assert.ok(failureViewModel("timeout").answer.includes("늦어지고"));
  assert.ok(failureViewModel("network").answer.includes("연결하지 못했어요"));
  assert.ok(failureViewModel("rate").answer.includes("예시 질문"));
  assert.ok(failureViewModel("invalid").answer.includes(String(MAX_QUESTION)));
  assert.equal(failureViewModel("blocked", "처리할 수 없는 질문이에요.").answer, "처리할 수 없는 질문이에요.");
  assert.equal(failureViewModel("timeout", "서버 상세 내부 정보").answer.includes("내부"), false);
  assert.equal(failureViewModel("busy", "x".repeat(500)).answer.length, 200);
  assert.ok(failureViewModel("unexpected-kind").answer.includes("답을 만들 수 없어요"));
  assert.ok(failureViewModel("offline").answer.includes("예시 질문"));
});

import { CHART_MAX_ROWS, LONG_ANSWER, chartOf, defaultView, followUps, isLongAnswer, tidyTitle } from "../js/view-model.js";

const hourly = (n) => Array.from({ length: n }, (_, i) => ({ hour: i, users: (i + 1) * 100 }));

test("갈래는 서버 meta.intent에서 온다(모르는 값은 null)", () => {
  assert.equal(toViewModel({ ...base, meta: { intent: "data" } }).lane, "data");
  assert.equal(toViewModel({ ...base, meta: { intent: "unknown" } }).lane, null);
  assert.equal(toViewModel({ ...base, meta: "x" }).lane, null);
  assert.equal(toViewModel(base).lane, null);
});

test("막대 그래프: 3~24행, 숫자 열이 있을 때만. 길이는 값/최댓값, 가장 큰 값 표시", () => {
  const t = toViewModel({ ...base, evidence_rows: hourly(4) }).table;
  assert.equal(t.chart.valueColumn, "users");
  assert.equal(t.chart.labelColumn, "hour");
  assert.deepEqual(t.chart.bars.map((b) => b.share), [0.25, 0.5, 0.75, 1]);
  assert.deepEqual(t.chart.bars.map((b) => b.top), [false, false, false, true]);
  assert.equal(t.chart.bars[3].label, "3");
  assert.equal(t.chart.bars[3].text, "400"); // 표와 같은 서식(1만 미만은 쉼표 없음)
  assert.equal(toViewModel({ ...base, evidence_rows: hourly(2) }).table.chart, null); // 너무 적음
  assert.equal(toViewModel({ ...base, evidence_rows: hourly(CHART_MAX_ROWS + 1) }).table.chart, null); // 너무 많음
  assert.notEqual(toViewModel({ ...base, evidence_rows: hourly(CHART_MAX_ROWS) }).table.chart, null);
});

test("막대 그래프를 그리지 않는 경우: 열 1개, 문자만 있는 표, 음수, 전부 0", () => {
  const rows = (f) => Array.from({ length: 4 }, (_, i) => f(i));
  assert.equal(toViewModel({ ...base, evidence_rows: rows((i) => ({ n: i + 1 })) }).table.chart, null);
  assert.equal(toViewModel({ ...base, evidence_rows: rows((i) => ({ a: "x", b: "y" + i })) }).table.chart, null);
  assert.equal(toViewModel({ ...base, evidence_rows: rows((i) => ({ a: i - 1, b: i - 2 })) }).table.chart, null); // 음수가 있는 열은 값 열이 못 된다
  assert.equal(toViewModel({ ...base, evidence_rows: rows(() => ({ a: "x", b: 0 })) }).table.chart, null);
  assert.equal(toViewModel({ ...base, evidence_rows: rows((i) => ({ a: "x", b: i === 1 ? null : 5 })) }).table.chart, null); // 빈 칸이 있으면 숫자 열이 아님
});

test("이름 칸은 값 열을 뺀 앞의 두 열을 합친다", () => {
  const rows = Array.from({ length: 3 }, (_, i) => ({ year: 2024, month: i + 1, place: "p", count: 10 * (i + 1) }));
  const c = toViewModel({ ...base, evidence_rows: rows }).table.chart;
  assert.equal(c.labelColumn, "year · month");
  assert.equal(c.bars[0].label, "2024 · 1");
});

test("처음 보기는 그래프(가능하면) 아니면 표", () => {
  assert.equal(defaultView(toViewModel({ ...base, evidence_rows: hourly(5) })), "chart");
  assert.equal(defaultView(toViewModel({ ...base, evidence_rows: [{ a: 1 }] })), "table");
  assert.equal(defaultView(toViewModel(base)), "table");
});

test("chartOf는 서버 값을 바꾸지 않는다(원본 숫자는 그대로, 길이만 비율)", () => {
  const raw = [[1, 215528], [2, 107764], [3, 0]];
  const cells = raw.map((r) => r.map((v) => ({ text: String(v), numeric: true })));
  const c = chartOf(["h", "u"], raw, cells);
  assert.deepEqual(c.bars.map((b) => b.share), [1, 0.5, 0]);
});

const ex = (lane, question) => ({ lane, question });
test("이어서 묻기: 이미 한 질문은 빼고 다른 갈래를 먼저 고른다", () => {
  const all = [ex("데이터", "d1"), ex("데이터", "d2"), ex("역사", "h1"), ex("소식", "n1"), ex("기관 정보", "o1")];
  const picked = followUps(all, ["h1"], "history");
  assert.equal(picked.length, 3);
  assert.deepEqual(picked.map((p) => p.question), ["d1", "n1", "o1"]);
  assert.ok(!picked.some((p) => p.question === "h1"));
  assert.deepEqual(followUps(all, all.map((e) => e.question), null), []);
  assert.deepEqual(followUps([ex("데이터", "d1"), ex("데이터", "d2")], [], "data").map((p) => p.question), ["d1", "d2"]); // 같은 갈래뿐이면 채워 넣는다
});

test("긴 답 줄이기는 근거 표가 따로 있을 때만", () => {
  const long = "가".repeat(LONG_ANSWER + 1);
  assert.equal(isLongAnswer(toViewModel({ ...base, answer: long, evidence_rows: [{ a: 1 }] })), true);
  assert.equal(isLongAnswer(toViewModel({ ...base, answer: long })), false); // 근거 표가 없으면 답이 전부이므로 줄이지 않는다
  assert.equal(isLongAnswer(toViewModel({ ...base, answer: "짧아요", evidence_rows: [{ a: 1 }] })), false);
  assert.equal(isLongAnswer(toViewModel({ ...base, unsupported_numbers: ["9"], evidence_rows: [{ a: 1 }] })), false); // 답을 숨긴 경우
});

test("제목 속 <br> 태그는 구분 글자로 바꾸고, 다른 태그는 글자 그대로 둔다", () => {
  assert.equal(tidyTitle("회사설립(자본금: 6억원)<br /> 스포츠교실 운영<br/>"), "회사설립(자본금: 6억원) · 스포츠교실 운영");
  assert.equal(tidyTitle("<BR>첫줄<br>둘째"), "첫줄 · 둘째");
  assert.equal(tidyTitle("<script>alert(1)</script>"), "<script>alert(1)</script>"); // 걸러내지 않는다(그리는 쪽이 textContent)
  assert.equal(tidyTitle("  여러   공백  "), "여러 공백");
  const vm = toViewModel({ ...base, documents: [{ date: "1990-07", title: "a<br />b", url: "", source: "s" }] });
  assert.equal(vm.documents[0].title, "a · b");
});

test("다시 시도는 잠깐의 문제에만 권한다(차단·길이·한도는 같은 질문을 다시 보내도 같다)", () => {
  for (const kind of ["timeout", "network", "busy", "server"]) assert.equal(failureViewModel(kind).retryable, true, kind);
  for (const kind of ["blocked", "invalid", "rate", "offline"]) assert.equal(failureViewModel(kind).retryable, false, kind);
  assert.equal(toViewModel(base).retryable, false); // 정상 답에는 단추가 없다
});

test("한도 안내는 서버가 준 문장을 쓴다(분당 제한과 하루 한도의 안내가 다르다)", () => {
  assert.equal(failureViewModel("rate", "오늘 받을 수 있는 질문을 모두 썼어요.").answer, "오늘 받을 수 있는 질문을 모두 썼어요.");
  assert.ok(failureViewModel("rate").answer.includes("예시 질문")); // 서버 문장이 없으면 기본 문구
});
