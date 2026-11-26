import { CalendarDays, Camera, ChevronUp, ExternalLink, Images, MapPin, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { StatusBadge } from './components'
import { isNoDerivatives } from './license'
import { Lightbox } from './Lightbox'
import { usePhotos } from './photos'
import { festivalTheme, imageSearchUrl } from './theme'
import type { Festival, PhotoResult } from './types'

export type SummaryState = { loading?: boolean; text?: string; error?: string }

/** 실제 사진이 있으면 사진, 없으면 축제 테마 색 타일(이모지) */
function Cover({
  festival: f,
  photos,
  onOpen,
}: {
  festival: Festival
  photos: PhotoResult | null
  onOpen: () => void
}) {
  const first = photos?.photos[0]
  const photo = first?.thumb
  const noCrop = !!first && isNoDerivatives(first.license)
  const t = festivalTheme(f.fstvl_nm)
  return (
    <figure
      className={`relative h-28 w-full shrink-0 overflow-hidden rounded-box bg-gradient-to-br sm:h-auto sm:w-36 ${t.gradient}`}
    >
      {photo ? (
        <button
          type="button"
          onClick={onOpen}
          aria-label={`${f.fstvl_nm} 사진 크게 보기`}
          className="absolute inset-0 cursor-zoom-in"
        >
          <img
            src={photo}
            alt={`${f.fstvl_nm} 사진`}
            loading="lazy"
            referrerPolicy="no-referrer"
            className={`h-full w-full transition ${noCrop ? 'object-contain bg-base-300' : 'object-cover hover:scale-105'}`}
          />
          {photos && photos.photos.length > 1 && (
            <span className="badge badge-neutral badge-sm absolute right-1 top-1 opacity-90">
              {photos.photos.length}장
            </span>
          )}
        </button>
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
  const [lightbox, setLightbox] = useState<number | null>(null)
  const photos = usePhotos(f.id)
  const summary = f.ai_summary || s?.text
  const hasPhotos = !!photos && photos.photos.length > 0

  return (
    <li className="card card-border bg-base-100 shadow-sm transition hover:shadow-md">
      <div className="card-body gap-4 p-4 sm:p-5">
        <div className="flex flex-col gap-4 sm:flex-row">
          <Cover festival={f} photos={photos} onOpen={() => setLightbox(0)} />

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
          {photos === null ? (
            <button disabled className="btn btn-ghost btn-sm">
              <span className="loading loading-spinner loading-xs" /> 사진 확인 중…
            </button>
          ) : hasPhotos ? (
            <button onClick={() => setLightbox(0)} className="btn btn-outline btn-sm">
              <Images size={14} /> 사진 열기
              <span className="badge badge-sm badge-ghost">{photos.photos.length}</span>
            </button>
          ) : (
            <button
              onClick={() => setShowGallery((v) => !v)}
              aria-expanded={showGallery}
              className="btn btn-ghost btn-sm"
            >
              {showGallery ? <ChevronUp size={14} /> : <Camera size={14} />}
              {showGallery ? '닫기' : '사진 찾기'}
            </button>
          )}
        </div>

        {showGallery && photos !== null && !hasPhotos && (
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

      {lightbox !== null && photos && photos.photos.length > 0 && (
        <Lightbox
          photos={photos.photos}
          index={Math.min(lightbox, photos.photos.length - 1)}
          title={f.fstvl_nm}
          note={photos.kind === 'region' ? `${photos.region} 지역 관광 사진 · 이 축제의 사진은 아니에요` : undefined}
          onIndex={setLightbox}
          onClose={() => setLightbox(null)}
        />
      )}
    </li>
  )
}
