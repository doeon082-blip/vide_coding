// 화면 값 정리(서버 응답 → 화면에 쓸 값)의 입구. 실제 코드는 view-model/ 폴더의 파일들에 나뉘어 있다.
// DOM을 쓰지 않는 순수 함수들이라서 브라우저 없이 node --test로 시험한다.
// 원칙: 서버가 준 값을 고치거나 계산하지 않는다. 다만 ① 숫자 미확인이면 한 줄 답을 숨기고(방어 한 겹 더),
// ② 링크는 허용 목록을 통과한 것만 링크로 만들고, ③ 막대 그래프의 길이(값/최댓값)만 '표시용'으로 계산한다.

export { CHART_MAX_ROWS, CHART_MIN_ROWS, LONG_ANSWER, MAX_QUESTION, NUMBER_NOTICE, VISIBLE_ROWS } from "./view-model/constants.js";
export { defaultView, isLongAnswer, toViewModel } from "./view-model/answer.js";
export { tidyTitle } from "./view-model/documents.js";
export { failureViewModel } from "./view-model/failure.js";
export { followUps } from "./view-model/follow-ups.js";
export { chartOf } from "./view-model/table.js";
