import { CalendarDays, Camera, ChevronUp, ExternalLink, MapPin, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { StatusBadge } from './components'
import { usePhotos } from './photos'
import { festivalTheme, imageSearchUrl } from './theme'
import type { Festival, PhotoResult } from './types'

export type SummaryState = { loading?: boolean; text?: string; error?: string }

/** 실제 사진이 있으면 사진, 없으면 축제 테마 색 타일(이모지) */
function Cover({ festival: f, photos }: { festival: Festival; photos: PhotoResult | null }) {
  const photo = photos?.photos[0]?.thumb
  const t = festivalTheme(f.fstvl_nm)
  return (
    <figure
      className={`relative h-28 w-full shrink-0 overflow-hidden rounded-box bg-gradient-to-br sm:h-auto sm:w-36 ${t.gradient}`}
    >
      {photo ? (
        <img
          src={photo}
          alt={`${f.fstvl_nm} 사진`}
          loading="lazy"
          referrerPolicy="no-referrer"
          className="absolute inset-0 h-full w-full object-cover"
        />
      ) : photos === null ? (
        <div className="skeleton h-full w-full rounded-none" />
      ) : (
        <div className="flex h-full w-full flex-col items-center justify-center gap-1 text-white">
          <span className="text-4xl drop-shadow" aria-hidden>
            {t.emoji}
          </span>
          <span className="text-xs font-semibold tracking-wide opacity-90">{t.label}</span>
        </div>
      )}
      {photo && photos?.kind === 'region' && (
        <span className="badge badge-neutral badge-sm absolute bottom-1 left-1 opacity-90">{photos.region} 지역</span>
      )}
    </figure>
  )
}

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
  const photos = usePhotos(f.id)
  const summary = f.ai_summary || s?.text

  return (
    <li className="card card-border bg-base-100 shadow-sm transition hover:shadow-md">
      <div className="card-body gap-4 p-4 sm:p-5">
        <div className="flex flex-col gap-4 sm:flex-row">
          <Cover festival={f} photos={photos} />

          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-3">
              <h2 className="text-lg font-bold leading-snug sm:text-xl">{f.fstvl_nm}</h2>
              <StatusBadge status={f.status} />
            </div>

            <dl className="mt-2 space-y-1 text-sm">
              <div className="flex items-center gap-2">
                <CalendarDays size={15} aria-hidden className="shrink-0 text-primary" />
                <dt className="sr-only">기간</dt>
                <dd className="font-medium">
                  {f.fstvl_start_date || '미정'} ~ {f.fstvl_end_date || '미정'}
                </dd>
              </div>
              {(f.opar || f.rdnmadr) && (
                <div className="flex items-start gap-2">
                  <MapPin size={15} aria-hidden className="mt-0.5 shrink-0 text-primary" />
                  <dt className="sr-only">장소</dt>
                  <dd className="opacity-80">{f.opar || f.rdnmadr}</dd>
                </div>
              )}
            </dl>

            {f.fstvl_co && <p className="mt-2 line-clamp-2 text-sm leading-relaxed opacity-70">{f.fstvl_co}</p>}
          </div>
        </div>

        {summary && (
          <div role="note" className="alert alert-soft alert-info items-start py-3 text-sm leading-relaxed">
            <Sparkles size={16} aria-hidden className="mt-0.5 shrink-0" />
            <div>
              <p className="text-xs font-semibold opacity-70">AI 한 줄 요약</p>
              <p>{summary}</p>
            </div>
          </div>
        )}
        {s?.error && (
          <div role="alert" className="alert alert-soft alert-error py-2 text-sm">
            {s.error}
          </div>
        )}

        <div className="card-actions border-t border-base-200 pt-3">
          {!summary && (
            <button onClick={() => onSummarize(f)} disabled={s?.loading} className="btn btn-primary btn-sm">
              {s?.loading ? <span className="loading loading-spinner loading-xs" /> : <Sparkles size={14} />}
              {s?.loading ? 'AI 요약 중…' : 'AI 한 줄 요약'}
            </button>
          )}
          <button
            onClick={() => setShowGallery((v) => !v)}
            aria-expanded={showGallery}
            className="btn btn-ghost btn-sm"
          >
            {showGallery ? <ChevronUp size={14} /> : <Camera size={14} />}
            사진 {showGallery ? '닫기' : '찾기'}
          </button>
        </div>

        {showGallery && (
          <div>
            {photos === null ? (
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {Array.from({ length: 3 }, (_, i) => (
                  <div key={i} className="skeleton aspect-[4/3] w-full" />
                ))}
              </div>
            ) : photos.photos.length > 0 ? (
              <>
                <p className="mb-2 text-sm font-medium">
                  {photos.kind === 'festival'
                    ? `📷 ${photos.matched_title || f.fstvl_nm} 사진`
                    : `📍 ${photos.region} 지역 관광 사진 (이 축제의 사진은 아니에요)`}
                </p>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {photos.photos.map((p) => (
                    <a key={p.url} href={p.url} target="_blank" rel="noopener noreferrer" className="group relative">
                      <img
                        src={p.thumb}
                        alt={p.caption || `${f.fstvl_nm} 관련 사진`}
                        loading="lazy"
                        referrerPolicy="no-referrer"
                        className="aspect-[4/3] w-full rounded-box bg-base-200 object-cover transition group-hover:opacity-90"
                      />
                      {photos.kind === 'region' && p.caption && (
                        <span className="absolute inset-x-0 bottom-0 truncate rounded-b-box bg-black/50 px-2 py-0.5 text-xs text-white">
                          {p.caption}
                        </span>
                      )}
                    </a>
                  ))}
                </div>
                <p className="mt-1 text-xs opacity-50">출처: 한국관광공사 (TourAPI)</p>
              </>
            ) : (
              <div className="rounded-box bg-base-200 p-4 text-sm">
                <p>한국관광공사에 등록된 사진을 찾지 못했어요.</p>
                <a
                  href={imageSearchUrl(f.fstvl_nm)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="link link-primary mt-2 inline-flex items-center gap-1"
                >
                  <ExternalLink size={14} aria-hidden /> 이미지 검색에서 “{f.fstvl_nm}” 보기
                </a>
              </div>
            )}
          </div>
        )}
      </div>
    </li>
  )
}
