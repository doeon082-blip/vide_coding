import { PartyPopper, Search, ShieldAlert, Wand2, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { correctQuery, fetchFestivals, searchFestivals, suggestFestivals, summarizeFestival } from './api'
import { CardSkeleton, Pagination } from './components'
import { ChatWidget } from './ChatWidget'
import { FestivalCard, type SummaryState } from './FestivalCard'
import { checkInput, RequestGuard } from './security'
import type { Festival, FestivalPage, StatusFilter } from './types'

const PAGE_SIZE = 10
const TABS: StatusFilter[] = ['전체', '진행중', '예정', '완료']

type Mode = { kind: 'list' } | { kind: 'search'; query: string }

export default function App() {
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<StatusFilter>('전체')
  const [data, setData] = useState<FestivalPage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<Mode>({ kind: 'list' })
  const [results, setResults] = useState<Festival[] | null>(null)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [searching, setSearching] = useState(false)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [didYouMean, setDidYouMean] = useState<string | null>(null)

  const [summaries, setSummaries] = useState<Record<string, SummaryState>>({})
  const guard = useRef(new RequestGuard())
  const typeaheadGuard = useRef(new RequestGuard(20, 10_000))

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchFestivals(page, PAGE_SIZE, status === '전체' ? undefined : status)
      .then((d) => !cancelled && setData(d))
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false))
    window.scrollTo({ top: 0, behavior: 'smooth' })
    return () => {
      cancelled = true
    }
  }, [page, status])

  /** 입력 검증(보안 프로토콜) 통과 시 정제된 값, 아니면 null + 에러 메시지 */
  function guarded(raw: string, g = guard.current, ai = false): string | null {
    const checked = checkInput(raw, ai)
    if (!checked.ok) {
      g.reportViolation()
      setSearchError(checked.message)
      setSuggestions([])
      return null
    }
    const blocked = g.allow()
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

  // 주소창 ?q=검색어 로 바로 검색 (공유/테스트용)
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get('q')
    if (q) {
      setQuery(q)
      void runSearch(q)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function runSearch(raw: string) {
    setSearchError(null)
    setDidYouMean(null)
    if (!raw.trim()) {
      resetToList()
      return
    }
    const q = guarded(raw)
    if (q === null) return
    setSearching(true)
    try {
      const [found, related] = await Promise.all([
        searchFestivals(q),
        suggestFestivals(q).catch(() => [] as string[]),
      ])
      setResults(found)
      setMode({ kind: 'search', query: q })
      setSuggestions(related)
      // 로컬 AI 오타 교정은 느릴 수 있어 결과를 막지 않고 뒤따라 표시
      correctQuery(q)
        .then((c) => c.corrected && setDidYouMean(c.corrected))
        .catch(() => undefined)
    } catch (err) {
      setResults(null)
      setSearchError((err as Error).message)
    } finally {
      setSearching(false)
    }
  }

  function resetToList() {
    setQuery('')
    setResults(null)
    setMode({ kind: 'list' })
    setSearchError(null)
    setSuggestions([])
    setDidYouMean(null)
  }

  function pickSuggestion(name: string) {
    setQuery(name)
    void runSearch(name)
  }

  function changeStatus(s: StatusFilter) {
    resetToList()
    setStatus(s)
    setPage(1)
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

  const items = results ?? data?.items
  const counts = data?.counts

  return (
    <div className="min-h-screen bg-base-200">
      <div className="navbar bg-base-100 shadow-sm">
        <div className="mx-auto flex w-full max-w-4xl items-center gap-2 px-4">
          <PartyPopper className="text-primary" aria-hidden />
          <span className="text-lg font-bold">전국 문화축제</span>
          <span className="badge badge-outline badge-sm ml-auto hidden sm:inline-flex">로컬 AI 큐레이션</span>
        </div>
      </div>

      <main className="mx-auto max-w-4xl px-4 py-8">
        <header className="mb-6">
          <h1 className="text-2xl font-bold sm:text-3xl">우리 동네 축제, 한눈에 🎉</h1>
          <p className="mt-1 text-sm opacity-70">공공데이터 기반 · 한국관광공사 사진 · 로컬 AI 큐레이션</p>
        </header>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            void runSearch(query)
          }}
          className="join w-full"
        >
          <label className="input join-item flex flex-1 items-center gap-2">
            <Search size={16} aria-hidden className="opacity-60" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              maxLength={100}
              placeholder="축제 검색 (오타가 있어도 비슷한 축제를 찾아요)"
              aria-label="축제 검색"
              className="grow"
            />
            {(results || query) && (
              <button type="button" onClick={resetToList} aria-label="검색 초기화" className="opacity-60 hover:opacity-100">
                <X size={16} />
              </button>
            )}
          </label>
          <button disabled={searching} className="btn btn-primary join-item">
            {searching ? <span className="loading loading-spinner loading-xs" /> : '검색'}
          </button>
        </form>

        {didYouMean && (
          <div role="status" className="alert alert-info alert-soft mt-3 py-2 text-sm">
            <Wand2 size={16} aria-hidden />
            <span>
              <span className="badge badge-info badge-sm mr-1">AI</span>
              혹시 <b>‘{didYouMean}’</b>
              을(를) 찾으셨나요?
            </span>
            <button onClick={() => pickSuggestion(didYouMean)} className="btn btn-xs btn-info">
              이걸로 검색
            </button>
          </div>
        )}

        {suggestions.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5" aria-label="연관검색어">
            <span className="text-xs opacity-60">연관검색어</span>
            {suggestions.map((sg) => (
              <button key={sg} onClick={() => pickSuggestion(sg)} className="btn btn-xs btn-soft btn-primary rounded-full">
                {sg}
              </button>
            ))}
          </div>
        )}

        {mode.kind === 'list' ? (
          <div role="tablist" aria-label="진행 상태" className="tabs tabs-box mt-6 w-fit bg-base-100">
            {TABS.map((t) => (
              <button
                key={t}
                role="tab"
                aria-selected={status === t}
                onClick={() => changeStatus(t)}
                className={`tab gap-1.5 ${status === t ? 'tab-active' : ''}`}
              >
                {t}
                {counts && <span className="badge badge-sm badge-ghost">{(counts[t] ?? 0).toLocaleString()}</span>}
              </button>
            ))}
          </div>
        ) : (
          <div className="mt-6 flex items-center justify-between gap-2 text-sm">
            <span className="opacity-70">
              {`‘${mode.query}’ 검색 결과 ${results?.length ?? 0}건`}
            </span>
            <button onClick={resetToList} className="btn btn-xs btn-ghost">
              목록으로
            </button>
          </div>
        )}

        {searchError && (
          <div role="alert" className="alert alert-warning alert-soft mt-4">
            <ShieldAlert size={18} aria-hidden />
            <span>{searchError}</span>
          </div>
        )}
        {error && (
          <div role="alert" className="alert alert-error alert-soft mt-4">
            <span>데이터를 불러오지 못했습니다: {error}</span>
          </div>
        )}

        <ul className="mt-4 space-y-3">
          {loading && !data && !results
            ? Array.from({ length: 4 }, (_, i) => <CardSkeleton key={i} />)
            : items?.map((f) => (
                <FestivalCard key={f.id} festival={f} summary={summaries[f.id]} onSummarize={onSummarize} />
              ))}
          {!loading && items?.length === 0 && <li className="py-12 text-center opacity-60">표시할 축제가 없습니다.</li>}
        </ul>

        {mode.kind === 'list' && data && data.total_pages > 1 && (
          <div className="mt-8">
            <Pagination page={page} totalPages={data.total_pages} onChange={setPage} />
          </div>
        )}
      </main>

      <ChatWidget onOpenFestival={pickSuggestion} />

      <footer className="footer footer-center p-6 text-xs opacity-60">
        <p>공공데이터포털 전국문화축제표준데이터 · 한국관광공사 TourAPI · Ollama · ChromaDB · DaisyUI</p>
      </footer>
    </div>
  )
}
