// 속성 이름 검사 시험(el 도우미의 안전 규칙 중 DOM 없이 시험할 수 있는 부분).
import assert from "node:assert/strict";
import test from "node:test";
import { isSafeAttr } from "../js/lib/dom.js";

test("이벤트·style·srcdoc 속성은 만들 수 없다", () => {
  for (const bad of ["onclick", "onerror", "ONLOAD", "style", "srcdoc", "formaction", "", "a b", "x=y", "1a", null, 5]) {
    assert.equal(isSafeAttr(bad), false, String(bad));
  }
});

test("일반 속성과 aria-·data- 속성은 허용", () => {
  for (const ok of ["class", "href", "aria-label", "data-x", "tabindex", "role", "type", "scope"]) {
    assert.equal(isSafeAttr(ok), true, ok);
  }
});

import { isLocalAsset } from "../js/lib/dom.js";

test("내부 그림 경로는 img/ 아래 svg·png만, 외부·이탈·스크립트 주소는 거부", () => {
  assert.equal(isLocalAsset("img/mark.svg"), true);
  assert.equal(isLocalAsset("img/lane-data.svg"), true);
  for (const bad of ["../img/mark.svg", "img/../secret.svg", "/img/mark.svg", "img/mark.svg?x=1", "img/mark.js", "img/MARK.svg", "https://evil.example/a.svg", "javascript:alert(1)", "data:image/svg+xml,<svg/>", "img//mark.svg", "", null, 5]) {
    assert.equal(isLocalAsset(bad), false, String(bad));
  }
});
