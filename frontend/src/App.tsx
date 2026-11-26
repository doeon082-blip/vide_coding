import { useEffect, useRef, useState } from 'react'
import { fetchFestivals, searchFestivals, suggestFestivals, summarizeFestival } from './api'
import { Pagination } from './components'
import { FestivalCard, type SummaryState } from './FestivalCard'
import { checkInput, RequestGuard } from './security'
import type { Festival, FestivalPage } from './types'

const PAGE_SIZE = 10

export default function App() {
  const [page, setPage] = useState(1)
  const [data, setData] = useState<FestivalPage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const [query, setQuery] = useState('')
  const [searchResults, setSearchResults] = useState<Festival[] | null>(null)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [searching, setSearching] = useState(false)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [summaries, setSummaries] = useState<Record<string, SummaryState>>({})
  const guard = useRef(new RequestGuard())
  const typeaheadGuard = useRef(new RequestGuard(20, 10_000))

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

  /** 입력 검증(보안 프로토콜) 통과 시 값, 아니면 null + 에러 메시지 설정 */
  function guarded(raw: string): string | null {
    const checked = checkInput(raw)
    if (!checked.ok) {
      guard.current.reportViolation()
      setSearchError(checked.message)
      setSuggestions([])
      return null
    }
    const blocked = guard.current.allow()
    if (blocked) {
      setSearchError(blocked)
      return null
    }
    return checked.value
  }

  // 입력 중 연관검색어 (디바운스 300ms, 검증 통과한 입력만 서버로 전송)
  useEffect(() => {
    const checked = checkInput(query)
    if (!checked.ok || checked.value.length < 2) {
      setSuggestions([])
      return
    }
    let cancelled = false
    const t = setTimeout(() => {
      if (typeaheadGuard.current.allow()) return
      suggestFestivals(checked.value)
        .then((s) => !cancelled && setSuggestions(s))
        .catch(() => !cancelled && setSuggestions([]))
    }, 300)
    return () => {
      cancelled = true
      clearTimeout(t)
    }
  }, [query])

  async function runSearch(raw: string) {
    setSearchError(null)
    if (!raw.trim()) {
      setSearchResults(null)
      return
    }
    const q = guarded(raw)
    if (q === null) return
    setSearching(true)
    try {
      const [results, related] = await Promise.all([
        searchFestivals(q),
        suggestFestivals(q).catch(() => [] as string[]),
      ])
      setSearchResults(results)
      setSuggestions(related)
    } catch (err) {
      setSearchResults(null)
      setSearchError((err as Error).message)
    } finally {
      setSearching(false)
    }
  }

  function pickSuggestion(name: string) {
    setQuery(name)
    void runSearch(name)
  }

  function clearSearch() {
    setQuery('')
    setSearchResults(null)
    setSearchError(null)
    setSuggestions([])
  }

  async function onSummarize(f: Festival) {
    setSummaries((s) => ({ ...s, [f.id]: { loading: true } }))
    try {
      const r = await summarizeFestival(f.id)
      setSummaries((s) => ({ ...s, [f.id]: { text: r.ai_summary } }))
    } catch (e) {
      setSummaries((s) => ({ ...s, [f.id]: { error: (e as Error).message } }))
    }
  }

  const items = searchResults ?? data?.items

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold sm:text-3xl">🎉 전국 문화축제 정보</h1>
        <p className="mt-1 text-sm text-slate-500">
          공공데이터 기반 · 로컬 AI 한 줄 요약
          {data && ` · 총 ${data.total.toLocaleString()}건 (${data.page} / ${data.total_pages} 페이지)`}
        </p>
      </header>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          void runSearch(query)
        }}
        className="flex gap-2"
      >
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          maxLength={100}
          placeholder="축제 검색 (오타가 있어도 비슷한 축제를 찾아요)"
          aria-label="축제 검색"
          className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500"
        />
        <button
          disabled={searching}
          className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-60"
        >
          {searching ? '검색 중…' : '검색'}
        </button>
        {(searchResults || query) && (
          <button
            type="button"
            onClick={clearSearch}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
          >
            초기화
          </button>
        )}
      </form>

      {suggestions.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5" aria-label="연관검색어">
          <span className="text-xs text-slate-500">🔎 연관검색어</span>
          {suggestions.map((s) => (
            <button
              key={s}
              onClick={() => pickSuggestion(s)}
              className="rounded-full bg-indigo-50 px-3 py-1 text-xs text-indigo-700 transition hover:bg-indigo-100"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {searchError && (
        <div role="alert" className="mt-4 rounded-lg bg-amber-50 p-4 text-sm font-medium text-amber-800">
          {searchError}
        </div>
      )}
      {error && (
        <div role="alert" className="mt-4 rounded-lg bg-red-50 p-4 text-sm text-red-700">
          데이터를 불러오지 못했습니다: {error}
        </div>
      )}

      <ul className={`mt-6 space-y-3 transition-opacity ${loading ? 'opacity-50' : ''}`}>
        {items?.map((f) => (
          <FestivalCard key={f.id} festival={f} summary={summaries[f.id]} onSummarize={onSummarize} />
        ))}
        {!loading && items?.length === 0 && (
          <li className="py-12 text-center text-slate-500">표시할 축제가 없습니다.</li>
        )}
      </ul>

      {!searchResults && data && data.total_pages > 1 && (
        <div className="mt-8">
          <Pagination page={page} totalPages={data.total_pages} onChange={setPage} />
        </div>
      )}
    </div>
  )
}
