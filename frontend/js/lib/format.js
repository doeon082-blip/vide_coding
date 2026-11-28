// 표시 도우미: 값을 고치거나 계산하지 않고 '보기 좋게만' 한다(숫자 대조는 서버가 이미 끝냈다).

// 큰 정수에만 쉼표를 넣는다. 연도(2024)·시각·번호는 쉼표가 붙으면 틀려 보이므로 열 이름으로 제외한다.
const NO_COMMA_COLUMN = /(^|_)(id|no|code|year|month|day|hour|date|zip)(_|$)|번호|코드|연도|년도|시각|일자/i;
const COMMA_FROM = 10000;

/** 표의 한 칸을 글자로. null은 '-', 큰 정수는 쉼표, 나머지는 서버 값 그대로. */
export function formatCell(column, value) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") {
    if (Number.isInteger(value) && Math.abs(value) >= COMMA_FROM && !NO_COMMA_COLUMN.test(String(column))) {
      return value.toLocaleString("en-US");
    }
    return String(value);
  }
  if (typeof value === "boolean") return value ? "예" : "아니요";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** 오른쪽 정렬할 칸인가(숫자). */
export function isNumeric(value) {
  return typeof value === "number" && Number.isFinite(value);
}

/** 서버가 준 '2026-11-30T10:00:00+09:00' 같은 시각에서 날짜(앞 10자)만. 모양이 다르면 null. */
export function dayOf(iso) {
  return typeof iso === "string" && /^\d{4}-\d{2}-\d{2}/.test(iso) ? iso.slice(0, 10) : null;
}
