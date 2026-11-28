// 근거 표(행·열)와 막대 그래프 값을 만든다. 서버 값은 바꾸지 않고 서식과 막대 길이(값/최댓값)만 계산한다.

import { CHART_MAX_ROWS, CHART_MIN_ROWS, MAX_COLUMNS, VISIBLE_ROWS } from "./constants.js";
import { isObject } from "./guards.js";
import { formatCell, isNumeric } from "../lib/format.js";

/**
 * 막대 그래프를 그릴 수 있으면 { labelColumn, valueColumn, bars }, 아니면 null.
 * 조건: 3~24행, 열 2개 이상, 모든 행이 숫자(0 이상)인 열이 있음. 값 열은 그런 열 중 마지막, 이름 칸은 나머지 열(최대 2개)을 합친 것.
 * 길이(share)는 값/최댓값으로 '표시용'으로만 계산한다. 서버의 값은 바꾸지 않고, 글자(text)는 표와 같은 서식이다.
 */
export function chartOf(columns, raw, cells) {
  const n = raw.length;
  if (n < CHART_MIN_ROWS || n > CHART_MAX_ROWS || columns.length < 2) return null;
  const numeric = columns.map((_, j) => j).filter((j) => raw.every((row) => isNumeric(row[j]) && row[j] >= 0));
  if (numeric.length === 0) return null;
  const valueIndex = numeric[numeric.length - 1];
  const labelIndexes = columns.map((_, j) => j).filter((j) => j !== valueIndex).slice(0, 2);
  const values = raw.map((row) => row[valueIndex]);
  const max = Math.max(...values);
  if (!(max > 0)) return null;
  return {
    labelColumn: labelIndexes.map((j) => columns[j]).join(" · "),
    valueColumn: columns[valueIndex],
    bars: raw.map((row, i) => ({
      label: labelIndexes.map((j) => cells[i][j].text).join(" · "),
      text: cells[i][valueIndex].text,
      share: Math.round((row[valueIndex] / max) * 10000) / 10000,
      top: row[valueIndex] === max,
    })),
  };
}

export function tableOf(rows) {
  const objects = Array.isArray(rows) ? rows.filter(isObject) : [];
  if (objects.length === 0) return null;
  const columns = [];
  for (const row of objects) {
    for (const key of Object.keys(row)) {
      if (!columns.includes(key) && columns.length < MAX_COLUMNS) columns.push(key);
    }
  }
  const raw = objects.map((row) => columns.map((c) => row[c]));
  const cells = raw.map((r) => r.map((v, j) => ({ text: formatCell(columns[j], v), numeric: isNumeric(v) })));
  return { columns, rows: cells, total: cells.length, visible: Math.min(cells.length, VISIBLE_ROWS), chart: chartOf(columns, raw, cells) };
}
