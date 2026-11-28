// 링크 허용 검사. 서버 응답·데이터 속 주소가 화면에서 링크가 되기 전에 반드시 이 함수를 거친다.
// 왜: 데이터 파일이나 AI 답에 'javascript:...'나 낯선 사이트 주소가 섞여 있으면 눌렀을 때 피해가 생긴다(XSS·피싱).
// 규칙: https만, 아래 허용 도메인(과 그 하위 도메인)만, 사용자 정보(user:pw@) 없이.

export const ALLOWED_HOSTS = Object.freeze(["data.go.kr", "ksponco.or.kr", "alio.go.kr"]);

/** 허용된 주소면 정리된 href 문자열을, 아니면 null을 돌려준다. */
export function safeUrl(raw) {
  if (typeof raw !== "string" || raw.length === 0 || raw.length > 2000) return null;
  let url;
  try {
    url = new URL(raw.trim());
  } catch {
    return null; // 주소 모양이 아니다
  }
  if (url.protocol !== "https:") return null; // javascript:, data:, http: 모두 여기서 걸린다
  if (url.username !== "" || url.password !== "") return null; // https://data.go.kr@evil.example 같은 위장
  const host = url.hostname.toLowerCase();
  // 'evil-data.go.kr'이나 'data.go.kr.evil.example'를 통과시키지 않도록 점(.)을 붙여 끝 일치만 본다
  const allowed = ALLOWED_HOSTS.some((h) => host === h || host.endsWith("." + h));
  return allowed ? url.href : null;
}
