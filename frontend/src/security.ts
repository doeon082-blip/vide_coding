/** 프론트엔드 보안 프로토콜: 입력 정제 → 위험 패턴 차단 → 요청 속도 제한 → 이미지 URL 화이트리스트 */

export const VIOLATION_MESSAGE = '규정위반: 허용되지 않는 입력입니다'
const MAX_LEN = 100

// 백엔드(main.py)와 동일한 규칙 — 서버가 최종 방어선이고, 여기서는 불필요한 요청을 먼저 차단한다.
const FORBIDDEN =
  /<\s*\/?\s*(script|iframe|img|svg|object)|javascript:|on\w+\s*=|\b(union\s+select|drop\s+table|insert\s+into|delete\s+from|select\s+.+\s+from)\b|(--|\/\*|\*\/|;\s*\w+\s*=)|\{\{|\$\{/i
// eslint-disable-next-line no-control-regex
const CONTROL_CHARS = /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/

// 프롬프트 인젝션 신호(서버 prompt_injection_defense.py 의 핵심 패턴과 동일한 의도). AI에게 보내는 질문에만 적용.
const INJECTION: RegExp[] = [
  /\b(?:ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}\b(?:instruction|prompt|rule|direction|guideline|command)/i,
  /(?:이전|위의?|앞(?:의|선)?|기존|모든|상기|지금까지(?:의)?)\s*(?:의\s*)?(?:지시|명령|지침|규칙|프롬프트|설정)[^.\n]{0,15}(?:무시|잊|취소|따르지|어기|우회)/,
  /(?:시스템|내부|숨겨진|초기)\s*(?:프롬프트|지시|지침|설정)/,
  /\b(?:system|hidden|initial)\s*prompt\b|\bjailbreak\b|\bdeveloper mode\b|탈옥|개발자\s*모드/i,
  /\b(?:you are now|from now on you|act as)\b|(?:너는|넌)\s*(?:이제|지금부터)|지금부터\s*(?:너는|넌)/i,
  /<\|?\s*(?:im_start|im_end|system|assistant)\s*\|?>|\[\/?INST\]|<<<|>>>/i,
]

export type InputCheck = { ok: true; value: string } | { ok: false; message: string }

/** 공백/유니코드 정규화 후 검사. 통과하면 정제된 값을 돌려준다. */
export function checkInput(raw: string, ai = false): InputCheck {
  // NFKC: 전각 문자 위장(＜ｓｃｒｉｐｔ＞)을 풀고, 제로폭 문자를 제거한 뒤 검사
  const value = raw
    .normalize('NFKC')
    // eslint-disable-next-line no-misleading-character-class
    .replace(/[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  if (
    value.length > MAX_LEN ||
    CONTROL_CHARS.test(raw) ||
    FORBIDDEN.test(value) ||
    (ai && INJECTION.some((rx) => rx.test(value)))
  ) {
    return { ok: false, message: VIOLATION_MESSAGE }
  }
  return { ok: true, value }
}

/** 슬라이딩 윈도우 속도 제한 + 위반 누적 시 일시 차단 */
export class RequestGuard {
  private hits: number[] = []
  private violations = 0
  private lockedUntil = 0

  private max: number
  private windowMs: number
  private maxViolations: number
  private lockMs: number

  constructor(max = 8, windowMs = 10_000, maxViolations = 3, lockMs = 30_000) {
    this.max = max
    this.windowMs = windowMs
    this.maxViolations = maxViolations
    this.lockMs = lockMs
  }

  /** 통과면 null, 아니면 사용자에게 보여줄 메시지 */
  allow(now = Date.now()): string | null {
    if (now < this.lockedUntil) {
      return `${VIOLATION_MESSAGE} (반복 위반으로 ${Math.ceil((this.lockedUntil - now) / 1000)}초간 차단)`
    }
    this.hits = this.hits.filter((t) => now - t < this.windowMs)
    if (this.hits.length >= this.max) return '요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.'
    this.hits.push(now)
    return null
  }

  reportViolation(now = Date.now()) {
    if (++this.violations >= this.maxViolations) {
      this.lockedUntil = now + this.lockMs
      this.violations = 0
    }
  }
}

const IMAGE_HOSTS = new Set(['tong.visitkorea.or.kr'])

/** https + 허용된 호스트의 이미지만 렌더링 */
export function isSafeImageUrl(url: string): boolean {
  try {
    const u = new URL(url)
    return u.protocol === 'https:' && IMAGE_HOSTS.has(u.hostname)
  } catch {
    return false
  }
}
