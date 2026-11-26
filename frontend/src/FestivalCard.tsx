import { Camera, ChevronUp, MapPin, CalendarDays, Sparkles } from 'lucide-react'
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
    <li className="card card-border bg-base-100 shadow-sm transition hover:shadow-md">
      <div className="card-body gap-3 p-4">
        <div className="flex gap-4">
          <figure className="hidden h-24 w-32 shrink-0 overflow-hidden rounded-box bg-base-200 sm:block">
            {thumb ? (
              <img
                src={thumb.urls[0]}
                alt={`${f.fstvl_nm} 사진`}
                loading="lazy"
                referrerPolicy="no-referrer"
                className="h-full w-full object-cover"
              />
            ) : (
              <div className="skeleton h-full w-full" />
            )}
          </figure>

          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-3">
              <h2 className="card-title text-base leading-snug sm:text-lg">{f.fstvl_nm}</h2>
              <StatusBadge status={f.status} />
            </div>
            <p className="mt-1 flex items-center gap-1.5 text-sm opacity-80">
              <CalendarDays size={14} aria-hidden />
              {f.fstvl_start_date || '미정'} ~ {f.fstvl_end_date || '미정'}
            </p>
            {(f.opar || f.rdnmadr) && (
              <p className="mt-0.5 flex items-center gap-1.5 truncate text-sm opacity-60">
                <MapPin size={14} aria-hidden className="shrink-0" />
                <span className="truncate">{f.opar || f.rdnmadr}</span>
              </p>
            )}
          </div>
        </div>

        {summary && (
          <div role="note" className="alert alert-soft alert-info py-2 text-sm">
            <Sparkles size={16} aria-hidden />
            <span>{summary}</span>
          </div>
        )}
        {s?.error && (
          <div role="alert" className="alert alert-soft alert-error py-2 text-sm">
            {s.error}
          </div>
        )}

        <div className="card-actions">
          {!summary && (
            <button onClick={() => onSummarize(f)} disabled={s?.loading} className="btn btn-primary btn-sm">
              {s?.loading ? <span className="loading loading-spinner loading-xs" /> : <Sparkles size={14} />}
              {s?.loading ? 'AI 요약 중…' : 'AI 한 줄 요약'}
            </button>
          )}
          <button
            onClick={() => setShowGallery((v) => !v)}
            aria-expanded={showGallery}
            className="btn btn-outline btn-sm"
          >
            {showGallery ? <ChevronUp size={14} /> : <Camera size={14} />}
            관련 사진 {showGallery ? '닫기' : '보기'}
          </button>
        </div>

        {showGallery && (
          <div>
            {!gallery ? (
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {Array.from({ length: 3 }, (_, i) => (
                  <div key={i} className="skeleton aspect-[4/3] w-full" />
                ))}
              </div>
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
                      className="aspect-[4/3] w-full rounded-box bg-base-200 object-cover"
                    />
                  ))}
                </div>
                <p className="mt-1 text-xs opacity-50">
                  {gallery.real
                    ? '출처: Wikimedia Commons (검색 결과라 축제와 무관한 사진이 섞일 수 있어요)'
                    : '축제 사진을 찾지 못해 임의 이미지(picsum.photos)를 표시합니다.'}
                </p>
              </>
            )}
          </div>
        )}
      </div>
    </li>
  )
}
