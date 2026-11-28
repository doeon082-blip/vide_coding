// 서버 호출: POST api/chaesan/ask. 시간 제한(30초)과 오류 분류를 맡는다.
// 주소는 상대 경로라 화면과 API가 같은 주소에 있으면 CORS 설정이 필요 없다.

export const ASK_URL = "api/chaesan/ask";
export const TIMEOUT_MS = 30_000;

/** HTTP 상태 → 오류 종류. 서버(app.py)가 쓰는 코드: 400 차단, 422 길이, 429 요청 제한, 503 혼잡·오류. */
export function classifyHttp(status) {
  if (status === 400) return "blocked";
  if (status === 422) return "invalid";
  if (status === 429) return "rate";
  if (status === 503) return "busy";
  return "server";
}

/** 질문을 보내고 { ok: true, data } 또는 { ok: false, kind, detail }을 돌려준다. 예외를 던지지 않는다. */
export async function askServer(question, { fetchImpl = fetch, timeoutMs = TIMEOUT_MS, url = ASK_URL } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetchImpl(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question }),
      signal: controller.signal,
      cache: "no-store",
      credentials: "omit", // 쿠키를 보내지 않는다(로그인이 없는 서비스)
      referrerPolicy: "no-referrer",
    });
    let body = null;
    try {
      body = await res.json();
    } catch {
      body = null; // 본문이 JSON이 아니어도 상태 코드로 분류한다
    }
    if (res.ok) return { ok: true, data: body };
    // 상세 문장은 서버가 일부러 일반 문장으로만 만든 detail(문자열)일 때만 전달한다. 422의 검증 목록은 버린다.
    return { ok: false, kind: classifyHttp(res.status), detail: typeof body?.detail === "string" ? body.detail : null };
  } catch (error) {
    return { ok: false, kind: error?.name === "AbortError" ? "timeout" : "network", detail: null };
  } finally {
    clearTimeout(timer);
  }
}
