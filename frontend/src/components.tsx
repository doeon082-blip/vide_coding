import type { FestivalStatus } from './types'

const BADGE: Record<FestivalStatus, string> = {
  진행중: 'bg-emerald-100 text-emerald-700 ring-emerald-200',
  예정: 'bg-sky-100 text-sky-700 ring-sky-200',
  완료: 'bg-slate-100 text-slate-500 ring-slate-200',
}

export function StatusBadge({ status }: { status: FestivalStatus | null }) {
  if (!status) return null
  return (
    <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${BADGE[status]}`}>
      {status}
    </span>
  )
}

/** Window of page numbers around the current page, e.g. 1 … 4 5 [6] 7 8 … 135 */
export function pageWindow(current: number, total: number, span = 2): (number | '…')[] {
  const pages = new Set([1, total])
  for (let p = current - span; p <= current + span; p++) if (p >= 1 && p <= total) pages.add(p)
  const sorted = [...pages].sort((a, b) => a - b)
  const out: (number | '…')[] = []
  sorted.forEach((p, i) => {
    if (i > 0 && p - sorted[i - 1] > 1) out.push('…')
    out.push(p)
  })
  return out
}

export function Pagination({
  page,
  totalPages,
  onChange,
}: {
  page: number
  totalPages: number
  onChange: (p: number) => void
}) {
  const btn =
    'min-w-9 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40'
  return (
    <nav className="flex flex-wrap items-center justify-center gap-1.5" aria-label="페이지 이동">
      <button className={btn} disabled={page <= 1} onClick={() => onChange(page - 1)}>
        이전
      </button>
      {pageWindow(page, totalPages).map((p, i) =>
        p === '…' ? (
          <span key={`e${i}`} className="px-1 text-slate-400">
            …
          </span>
        ) : (
          <button
            key={p}
            aria-current={p === page ? 'page' : undefined}
            className={`${btn} ${p === page ? '!border-indigo-600 !bg-indigo-600 text-white hover:!bg-indigo-600' : ''}`}
            onClick={() => onChange(p)}
          >
            {p}
          </button>
        ),
      )}
      <button className={btn} disabled={page >= totalPages} onClick={() => onChange(page + 1)}>
        다음
      </button>
    </nav>
  )
}
