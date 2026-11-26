import type { FestivalPage, SummaryResult } from './types'

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

export const summarizeFestival = (id: number) =>
  request<SummaryResult>(`/api/festivals/${id}/summarize`, { method: 'POST' })
