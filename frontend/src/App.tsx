import { useEffect, useState } from 'react'
import { fetchFestivals, summarizeFestival } from './api'
import { Pagination, StatusBadge } from './components'
import type { Festival, FestivalPage } from './types'

const PAGE_SIZE = 10

type SummaryState = { loading?: boolean; text?: string; error?: string }

export default function App() {
  const [page, setPage] = useState(1)
  const [data, setData] = useState<FestivalPage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [summaries, setSummaries] = useState<Record<number, SummaryState>>({})

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchFestivals(page, PAGE_SIZE)
      .then((d) => !cancelled && setData(d))
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false))
    window.scrollTo({ top: 0, behavior: 'smooth' })
    return () => {
      cancelled = true
    }
  }, [page])

  async function onSummarize(f: Festival) {
    setSummaries((s) => ({ ...s, [f.id]: { loading: true } }))
    try {
      const r = await summarizeFestival(f.id)
      setSummaries((s) => ({ ...s, [f.id]: { text: r.ai_summary } }))
    } catch (e) {
      setSummaries((s) => ({ ...s, [f.id]: { error: (e as Error).message } }))
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold sm:text-3xl">🎉 전국 문화축제 정보</h1>
        <p className="mt-1 text-sm text-slate-500">
          공공데이터 기반 · 로컬 AI 한 줄 요약
          {data && ` · 총 ${data.total.toLocaleString()}건 (${data.page} / ${data.total_pages} 페이지)`}
        </p>
      </header>

      {error && (
        <div role="alert" className="mb-4 rounded-lg bg-red-50 p-4 text-sm text-red-700">
          데이터를 불러오지 못했습니다: {error}
        </div>
      )}

      <ul className={`space-y-3 transition-opacity ${loading ? 'opacity-50' : ''}`}>
        {data?.items.map((f) => {
          const s = summaries[f.id]
          const summary = f.ai_summary ?? s?.text
          return (
            <li key={f.id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                <h2 className="text-base font-semibold leading-snug sm:text-lg">{f.fstvl_nm}</h2>
                <StatusBadge status={f.status} />
              </div>
              <p className="mt-1 text-sm text-slate-600">
                📅 {f.fstvl_start_date || '미정'} ~ {f.fstvl_end_date || '미정'}
              </p>
              {(f.opar || f.rdnmadr) && (
                <p className="mt-0.5 truncate text-sm text-slate-500">📍 {f.opar || f.rdnmadr}</p>
              )}

              <div className="mt-3 flex flex-wrap items-center gap-3">
                {summary ? (
                  <p className="rounded-lg bg-indigo-50 px-3 py-2 text-sm text-indigo-900">✨ {summary}</p>
                ) : (
                  <button
                    onClick={() => onSummarize(f)}
                    disabled={s?.loading}
                    className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:opacity-60"
                  >
                    {s?.loading ? 'AI 요약 중…' : '✨ AI 한 줄 요약'}
                  </button>
                )}
                {s?.error && <p className="text-sm text-red-600">{s.error}</p>}
              </div>
            </li>
          )
        })}
        {!loading && data?.items.length === 0 && (
          <li className="py-12 text-center text-slate-500">표시할 축제가 없습니다.</li>
        )}
      </ul>

      {data && data.total_pages > 1 && (
        <div className="mt-8">
          <Pagination page={page} totalPages={data.total_pages} onChange={setPage} />
        </div>
      )}
    </div>
  )
}
