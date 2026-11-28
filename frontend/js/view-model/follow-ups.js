// 답 아래에 보여 줄 '이어서 물어볼 만한 질문' 고르기.

import { laneKeyByLabel } from "../lib/lane.js";

/**
 * 답 아래에 보여 줄 '이어서 물어볼 만한 질문'(최대 limit개). 이미 한 질문은 빼고, 다른 갈래를 먼저 고른다(다양하게).
 * examples: [{ lane: "데이터", question: "..." }], asked: 이미 물은 질문 글자들.
 */
export function followUps(examples, asked, currentLane, limit = 3) {
  const done = new Set(asked);
  const fresh = examples.filter((e) => !done.has(e.question));
  const out = [];
  const seen = new Set([currentLane]);
  for (const ex of fresh) {
    const key = laneKeyByLabel(ex.lane);
    if (!seen.has(key) && out.length < limit) {
      out.push(ex);
      seen.add(key);
    }
  }
  for (const ex of fresh) if (out.length < limit && !out.includes(ex)) out.push(ex);
  return out;
}
