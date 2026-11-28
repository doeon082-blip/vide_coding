// 갈래 표시 시험: 서버 intent와 화면 이름이 어긋나지 않는지.
import assert from "node:assert/strict";
import test from "node:test";
import { LANES, laneClass, laneKeyByLabel, laneKeyOf, laneLabel } from "../app/chaesan/web/js/lib/lane.js";

test("서버 intent 다섯 갈래만 키가 되고 unknown·낯선 값은 null", () => {
  for (const key of ["history", "facility", "news", "org", "data"]) assert.equal(laneKeyOf(key), key);
  for (const bad of ["unknown", "", null, undefined, 5, "__proto__", "constructor", "toString"]) assert.equal(laneKeyOf(bad), null, String(bad));
});

test("한글 이름 ↔ 키, 클래스 이름", () => {
  assert.equal(laneKeyByLabel("시설·이용"), "facility");
  assert.equal(laneKeyByLabel("없는 갈래"), null);
  assert.equal(laneClass("data"), "lane-data");
  assert.equal(laneClass(null), "lane-other");
  assert.equal(laneLabel(null), "답변");
  assert.equal(Object.keys(LANES).length, 5);
});
