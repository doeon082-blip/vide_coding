// 출처 목록 값: 데이터 이름(번호)·자료 기간·링크(허용 목록을 통과한 것만).

import { isObject, text } from "./guards.js";
import { safeUrl } from "../lib/safe-url.js";

export function sourcesOf(sources) {
  if (!Array.isArray(sources)) return [];
  return sources.filter(isObject).map((s) => ({
    label: s.id ? `${text(s.name)}(${text(s.id)})` : text(s.name),
    period: text(s.period),
    href: safeUrl(s.url),
  }));
}
