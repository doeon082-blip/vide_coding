// 관련 문서(연혁·소식·FAQ 등) 목록 값. 링크는 허용 목록을 통과한 것만 href가 된다.

import { MAX_DOCS } from "./constants.js";
import { isObject, text } from "./guards.js";
import { safeUrl } from "../lib/safe-url.js";

/** 자료 제목 속 줄바꿈 태그(<br />)를 읽기 좋은 구분으로 바꾼다. 그 밖의 글자는 그대로 둔다(해석하지 않고 글자로만 보이므로 안전). */
export function tidyTitle(value) {
  return value.replace(/<br\s*\/?>/gi, " · ").replace(/\s+/g, " ").replace(/^( · )+|( · )+$/g, "").trim();
}

export function documentsOf(docs) {
  if (!Array.isArray(docs)) return [];
  return docs
    .filter(isObject)
    .slice(0, MAX_DOCS)
    .map((d) => ({
      dateText: text(d.date) || "날짜 없음",
      title: tidyTitle(text(d.title)) || "(제목 없음)",
      source: text(d.source),
      href: safeUrl(d.url), // 허용 목록 밖이면 null → 글자로만 보인다
      bodyMissing: d.body_available === false,
    }));
}
