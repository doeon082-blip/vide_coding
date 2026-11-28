// 서버 응답이 약속한 모양이 아닐 수 있어서 값을 읽기 전에 쓰는 작은 검사들.

export const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
export const text = (v) => (typeof v === "string" ? v : v === null || v === undefined ? "" : String(v));
