// 화면 값 정리에 쓰는 상수와 고정 문구. 서버와 맞춰야 하는 값은 주석으로 표시하고 테스트가 서버 값과 비교한다.

export const MAX_QUESTION = 200; // 서버 core.config.MAX_QUESTION_LEN과 같아야 한다(테스트가 비교)
export const VISIBLE_ROWS = 20;
export const CHART_MIN_ROWS = 3;
export const CHART_MAX_ROWS = 24;
export const MAX_COLUMNS = 12;
export const MAX_DOCS = 20;
export const LONG_ANSWER = 140; // 근거 표가 따로 있을 때 이보다 긴 한 줄 답은 처음에 줄여 보인다

// 서버 status(engine.Status)와 1:1. tone은 글자와 함께 색을 고르는 데만 쓴다.
export const STATUS = {
  answered: { label: "답변", tone: "ok" },
  unknown: { label: "근거를 찾지 못했어요", tone: "warn" },
  clarify: { label: "확인이 필요해요", tone: "warn" },
  planned: { label: "아직 연결하지 않은 자료예요", tone: "warn" },
  blocked: { label: "처리할 수 없는 질문이에요", tone: "err" },
  error: { label: "오류", tone: "err" },
};
export const ALERT_BADGE = /갱신 안 됨|확인하세요|다를 수|본문 없음|기간 정보 없음/;
export const NUMBER_NOTICE = "숫자를 확인하지 못해 근거 표만 보여 드려요.";

export const FAILURES = {
  timeout: "답이 늦어지고 있어요. 다시 시도해 주세요.",
  network: "서버에 연결하지 못했어요. 인터넷 연결을 확인하고 다시 시도해 주세요.",
  rate: "질문이 너무 많아요. 잠시 후 다시 물어봐 주세요. 예시 질문은 계속 볼 수 있어요.",
  invalid: `질문은 1자 이상 ${MAX_QUESTION}자 이하로 써 주세요.`,
  blocked: "처리할 수 없는 질문이에요. 다른 말로 물어봐 주세요.",
  busy: "지금은 질문이 많아요. 잠시 후 다시 물어봐 주세요.",
  server: "지금은 답을 만들 수 없어요. 잠시 후 다시 시도해 주세요.",
  offline: "서버 없이 보는 예비 화면이라 직접 질문할 수 없어요. 예시 질문을 눌러 보세요.",
};
