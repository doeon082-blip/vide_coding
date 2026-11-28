// 질문 갈래(서버 intent) ↔ 화면 표시. 서버 planner.INTENTS(history·facility·news·org·data·unknown)와 같은 이름을 쓴다(테스트가 비교).

export const LANES = Object.freeze({
  history: { label: "역사" },
  facility: { label: "시설·이용" },
  news: { label: "소식" },
  org: { label: "기관 정보" },
  data: { label: "데이터" },
});

/** 서버 intent가 다섯 갈래 중 하나면 그 키, 아니면(unknown 등) null. */
export function laneKeyOf(intent) {
  return typeof intent === "string" && Object.hasOwn(LANES, intent) ? intent : null;
}

/** 예시 파일의 한글 갈래 이름('시설·이용') → 키. 모르는 이름이면 null. */
export function laneKeyByLabel(label) {
  return Object.keys(LANES).find((key) => LANES[key].label === label) ?? null;
}

/** CSS 클래스(색·아이콘). 갈래를 모르면 중립 클래스. */
export function laneClass(key) {
  return key ? `lane-${key}` : "lane-other";
}

export function laneLabel(key) {
  return key ? LANES[key].label : "답변";
}
