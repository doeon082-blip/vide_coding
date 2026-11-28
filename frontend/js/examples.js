// 예시 질문과 미리 계산한 답(data/examples.json)을 읽는다. 읽지 못해도 질문창은 동작한다.

import { dayOf } from "./lib/format.js";

export async function loadExamples(url = "data/examples.json") {
  try {
    const res = await fetch(url, { cache: "no-store", credentials: "omit" });
    if (!res.ok) return [];
    const data = await res.json();
    const generatedAt = dayOf(data.generated_at);
    const list = Array.isArray(data.examples) ? data.examples : [];
    return list.filter((e) => e && typeof e.lane === "string" && typeof e.question === "string").map((e) => ({ ...e, generatedAt }));
  } catch {
    return [];
  }
}
