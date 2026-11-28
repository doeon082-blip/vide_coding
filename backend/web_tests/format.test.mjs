// 표시 도우미 시험: 값을 바꾸지 않고 보기 좋게만 하는지.
import assert from "node:assert/strict";
import test from "node:test";
import { dayOf, formatCell, isNumeric } from "../app/chaesan/web/js/lib/format.js";

test("큰 정수에만 쉼표, 연도·시각·번호 열은 그대로", () => {
  assert.equal(formatCell("users", 215528), "215,528");
  assert.equal(formatCell("users", 9999), "9999");
  assert.equal(formatCell("year", 2024), "2024");
  assert.equal(formatCell("data_id", 15133891), "15133891");
  assert.equal(formatCell("total", -120000), "-120,000");
});

test("소수·문자열·null·불리언은 서버 값 그대로(또는 표시만)", () => {
  assert.equal(formatCell("rate", 3.5), "3.5");
  assert.equal(formatCell("name", "올림픽공원"), "올림픽공원");
  assert.equal(formatCell("name", null), "-");
  assert.equal(formatCell("flag", true), "예");
  assert.equal(formatCell("name", "<script>alert(1)</script>"), "<script>alert(1)</script>"); // 걸러내지 않고 글자 그대로(그리는 쪽이 textContent)
});

test("isNumeric·dayOf", () => {
  assert.equal(isNumeric(1), true);
  assert.equal(isNumeric("1"), false);
  assert.equal(isNumeric(NaN), false);
  assert.equal(dayOf("2026-11-30T10:00:00+09:00"), "2026-11-30");
  assert.equal(dayOf("어제"), null);
  assert.equal(dayOf(null), null);
});
