import type { Festival, FestivalPage, SummaryResult } from './types'

const BASE = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '')

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
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
