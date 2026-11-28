// 링크 허용 검사 시험: 허용 도메인만 통과하고 위장 주소는 모두 막는지.
import assert from "node:assert/strict";
import test from "node:test";
import { safeUrl } from "../js/lib/safe-url.js";

test("허용 도메인(하위 도메인 포함)의 https 주소는 통과", () => {
  assert.equal(safeUrl("https://www.data.go.kr/data/15133891/fileData.do"), "https://www.data.go.kr/data/15133891/fileData.do");
  assert.equal(safeUrl("https://www.ksponco.or.kr/olympicpark/board.es?mid=a20601000"), "https://www.ksponco.or.kr/olympicpark/board.es?mid=a20601000");
  assert.ok(safeUrl("https://alio.go.kr/item/itemOrganList.do"));
  assert.ok(safeUrl("https://data.go.kr/"));
});

test("위험한 주소는 모두 null", () => {
  for (const bad of [
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "http://www.data.go.kr/", // https만
    "https://evil.example/data.go.kr",
    "https://data.go.kr.evil.example/",
    "https://evil-data.go.kr/",
    "https://notdata.go.kr/",
    "https://data.go.kr@evil.example/",
    "https://user:pw@www.data.go.kr/",
    "//www.data.go.kr/",
    "/relative/path",
    "ftp://www.data.go.kr/",
    "",
    "   ",
    null,
    undefined,
    42,
    {},
    "https://www.data.go.kr/" + "a".repeat(2000),
  ]) {
    assert.equal(safeUrl(bad), null, String(bad).slice(0, 40));
  }
});

test("앞뒤 공백·대문자 호스트는 정리해서 판단", () => {
  assert.ok(safeUrl("  https://WWW.DATA.GO.KR/x  "));
});
