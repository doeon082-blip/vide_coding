import { useState } from 'react'
import { StatusBadge } from './components'
import { usePhotos } from './photos'
import type { Festival } from './types'

export type SummaryState = { loading?: boolean; text?: string; error?: string }

export function FestivalCard({
  festival: f,
  summary: s,
  onSummarize,
}: {
  festival: Festival
  summary?: SummaryState
  onSummarize: (f: Festival) => void
}) {
  const [showGallery, setShowGallery] = useState(false)
  const thumb = usePhotos(f.id, f.fstvl_nm, 1)
  const gallery = usePhotos(f.id, f.fstvl_nm, 6, showGallery)
  const summary = f.ai_summary || s?.text

  return (
    <li className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex gap-4">
        <div className="hidden h-24 w-32 shrink-0 overflow-hidden rounded-lg bg-slate-100 sm:block">
          {thumb && (
            <img
              src={thumb.urls[0]}
              alt={`${f.fstvl_nm} 사진`}
              loading="lazy"
              referrerPolicy="no-referrer"
              className="h-full w-full object-cover"
            />
          )}
        </div>

        <div className="min-w-0 flex-1">
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

          <div className="mt-3 flex flex-wrap items-center gap-2">
            {!summary && (
              <button
                onClick={() => onSummarize(f)}
                disabled={s?.loading}
                className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:opacity-60"
              >
                {s?.loading ? 'AI 요약 중…' : '✨ AI 한 줄 요약'}
              </button>
            )}
            <button
              onClick={() => setShowGallery((v) => !v)}
              aria-expanded={showGallery}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-50"
            >
              📷 관련 사진 {showGallery ? '닫기' : '보기'}
            </button>
            {s?.error && <p className="text-sm text-red-600">{s.error}</p>}
          </div>
          {summary && (
            <p className="mt-2 rounded-lg bg-indigo-50 px-3 py-2 text-sm text-indigo-900">✨ {summary}</p>
          )}
        </div>
      </div>

      {showGallery && (
        <div className="mt-4">
          {!gallery ? (
            <p className="text-sm text-slate-500">사진을 불러오는 중…</p>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {gallery.urls.map((u) => (
                  <img
                    key={u}
                    src={u}
                    alt={`${f.fstvl_nm} 관련 사진`}
                    loading="lazy"
                    referrerPolicy="no-referrer"
                    className="aspect-[4/3] w-full rounded-lg bg-slate-100 object-cover"
                  />
                ))}
              </div>
              <p className="mt-1 text-xs text-slate-400">
                {gallery.real
                  ? '출처: Wikimedia Commons (검색 결과라 축제와 무관한 사진이 섞일 수 있어요)'
                  : '축제 사진을 찾지 못해 임의 이미지(picsum.photos)를 표시합니다.'}
              </p>
            </>
          )}
        </div>
      )}
    </li>
  )
}
