// 예비 모드 판단 시험.
import assert from "node:assert/strict";
import test from "node:test";
import { detectOffline } from "../js/lib/mode.js";

test("?offline=1 이면 예비 모드", () => {
  assert.equal(detectOffline("?offline=1", "localhost"), true);
  assert.equal(detectOffline("?offline=0", "localhost"), false);
  assert.equal(detectOffline("", "localhost"), false);
});

test("github.io 정적 호스팅은 자동으로 예비 모드, 비슷한 이름은 아니다", () => {
  assert.equal(detectOffline("", "someone.github.io"), true);
  assert.equal(detectOffline("", "SOMEONE.GITHUB.IO"), true);
  assert.equal(detectOffline("", "github.io.evil.example"), false);
  assert.equal(detectOffline("", "notgithub.io"), false);
  assert.equal(detectOffline("", undefined), false);
});
