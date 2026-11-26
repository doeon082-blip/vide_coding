import { CalendarCheck, CalendarClock, CircleCheck, type LucideIcon } from 'lucide-react'
import type { FestivalStatus } from './types'

const BADGE: Record<FestivalStatus, { cls: string; Icon: LucideIcon }> = {
  진행중: { cls: 'badge-success', Icon: CalendarCheck },
  예정: { cls: 'badge-info', Icon: CalendarClock },
  완료: { cls: 'badge-ghost', Icon: CircleCheck },
}

export function StatusBadge({ status }: { status: FestivalStatus | null }) {
  if (!status) return null
  const { cls, Icon } = BADGE[status]
  return (
    <span className={`badge ${cls} shrink-0 gap-1 font-semibold`}>
      <Icon size={12} aria-hidden /> {status}
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
  return (
    <nav className="flex justify-center" aria-label="페이지 이동">
      <div className="join flex-wrap justify-center">
        <button className="btn join-item btn-sm" disabled={page <= 1} onClick={() => onChange(page - 1)}>
          «&nbsp;이전
        </button>
        {pageWindow(page, totalPages).map((p, i) =>
          p === '…' ? (
            <button key={`e${i}`} className="btn join-item btn-sm btn-disabled" aria-hidden>
              …
            </button>
          ) : (
            <button
              key={p}
              aria-current={p === page ? 'page' : undefined}
              className={`btn join-item btn-sm ${p === page ? 'btn-primary' : ''}`}
              onClick={() => onChange(p)}
            >
              {p}
            </button>
          ),
        )}
        <button className="btn join-item btn-sm" disabled={page >= totalPages} onClick={() => onChange(page + 1)}>
          다음&nbsp;»
        </button>
      </div>
    </nav>
  )
}

export function CardSkeleton() {
  return (
    <li className="card card-border bg-base-100 p-4">
      <div className="flex gap-4">
        <div className="skeleton hidden h-24 w-32 shrink-0 sm:block" />
        <div className="flex flex-1 flex-col gap-3">
          <div className="skeleton h-5 w-2/3" />
          <div className="skeleton h-4 w-1/3" />
          <div className="skeleton h-8 w-32" />
        </div>
      </div>
    </li>
  )
}
