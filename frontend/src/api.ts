import type { Festival, FestivalPage, PhotoResult, SummaryResult } from './types'

const ENV_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

/** 배포본은 public/config.json 의 apiBaseUrl 을 우선 사용 (터널 주소가 바뀌어도 재빌드 불필요) */
let basePromise: Promise<string> | null = null
function getBase(): Promise<string> {
  if (import.meta.env.DEV) return Promise.resolve(ENV_BASE.replace(/\/$/, '')) // 로컬 개발은 .env 사용
  basePromise ??= fetch(`${import.meta.env.BASE_URL}config.json`, { cache: 'no-store' })
    .then((r) => (r.ok ? r.json() : {}))
    .then((c: { apiBaseUrl?: string }) => (c.apiBaseUrl || ENV_BASE).replace(/\/$/, ''))
    .catch(() => ENV_BASE.replace(/\/$/, ''))
  return basePromise
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${await getBase()}${path}`, init)
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export const fetchFestivals = (page: number, size = 10) =>
  request<FestivalPage>(`/api/festivals?page=${page}&size=${size}`)

export const searchFestivals = (q: string, limit = 10) =>
  request<Festival[]>(`/api/festivals/search?q=${encodeURIComponent(q)}&limit=${limit}`)

/** 연관검색어(오타 교정 포함) */
export const suggestFestivals = (q: string, limit = 6) =>
  request<string[]>(`/api/festivals/suggest?q=${encodeURIComponent(q)}&limit=${limit}`)

export const summarizeFestival = (id: string) =>
  request<SummaryResult>(`/api/festivals/${id}/summarize`, { method: 'POST' })

/** 한국관광공사 TourAPI 기반 축제/지역 사진 */
export const fetchPhotos = (id: string) => request<PhotoResult>(`/api/festivals/${id}/photos`)
