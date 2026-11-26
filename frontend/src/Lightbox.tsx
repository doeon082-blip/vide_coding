import { ChevronLeft, ChevronRight, ExternalLink, X } from 'lucide-react'
import { useCallback, useEffect, useRef } from 'react'
import { KOGL_INFO_URL, koglLabel } from './license'
import type { Photo } from './types'

/** 사진 확대 보기: 좌우 버튼 · 키보드(←/→/Esc) · 터치 스와이프 · 배경 클릭으로 닫기 */
export function Lightbox({
  photos,
  index,
  title,
  note,
  onIndex,
  onClose,
}: {
  photos: Photo[]
  index: number
  title: string
  note?: string
  onIndex: (i: number) => void
  onClose: () => void
}) {
  const n = photos.length
  const closeRef = useRef<HTMLButtonElement>(null)
  const touchX = useRef<number | null>(null)

  const go = useCallback((delta: number) => onIndex((index + delta + n) % n), [index, n, onIndex])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      else if (e.key === 'ArrowLeft') go(-1)
      else if (e.key === 'ArrowRight') go(1)
    }
    window.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden' // 뒤쪽 스크롤 잠금
    closeRef.current?.focus()
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [go, onClose])

  // 이웃 사진 미리 불러오기 → 넘길 때 깜빡임 방지
  useEffect(() => {
    for (const d of [-1, 1]) {
      const img = new Image()
      img.src = photos[(index + d + n) % n].url
    }
  }, [index, n, photos])

  const photo = photos[index]
  const navBtn =
    'btn btn-circle btn-ghost absolute top-1/2 -translate-y-1/2 border-white/20 bg-black/40 text-white hover:bg-black/70'

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`${title} 사진 ${index + 1} / ${n}`}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-2 sm:p-6"
      onClick={onClose}
      onTouchStart={(e) => (touchX.current = e.touches[0].clientX)}
      onTouchEnd={(e) => {
        if (touchX.current === null) return
        const dx = e.changedTouches[0].clientX - touchX.current
        touchX.current = null
        if (Math.abs(dx) > 50) go(dx < 0 ? 1 : -1)
      }}
    >
      <button ref={closeRef} onClick={onClose} aria-label="닫기" className="btn btn-circle btn-ghost absolute right-3 top-3 text-white">
        <X />
      </button>

      <figure className="flex max-h-full max-w-5xl flex-col items-center gap-3" onClick={(e) => e.stopPropagation()}>
        <img
          key={photo.url}
          src={photo.url}
          alt={photo.caption || title}
          referrerPolicy="no-referrer"
          className="max-h-[78vh] w-auto max-w-full rounded-lg object-contain shadow-2xl"
        />
        <figcaption className="max-w-full text-center text-sm text-white/90">
          <p className="font-semibold">{photo.caption || title}</p>
          {note && <p className="mt-0.5 text-xs text-white/60">{note}</p>}
          <p className="mt-0.5 text-xs text-white/60">
            출처: 한국관광공사 ·{' '}
            <a href={KOGL_INFO_URL} target="_blank" rel="noopener noreferrer" className="underline">
              {koglLabel(photo.license)}
            </a>
          </p>
          <p className="mt-1 flex items-center justify-center gap-3 text-xs text-white/60">
            <span aria-live="polite">
              {index + 1} / {n}
            </span>
            <a href={photo.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline">
              <ExternalLink size={12} aria-hidden /> 원본 보기
            </a>
          </p>
        </figcaption>

        {n > 1 && (
          <div className="flex max-w-full gap-1.5 overflow-x-auto pb-1" role="tablist" aria-label="사진 목록">
            {photos.map((p, i) => (
              <button
                key={p.url}
                role="tab"
                aria-selected={i === index}
                aria-label={`${i + 1}번 사진`}
                onClick={() => onIndex(i)}
                className={`h-12 w-16 shrink-0 overflow-hidden rounded-md border-2 ${i === index ? 'border-primary' : 'border-transparent opacity-60 hover:opacity-100'}`}
              >
                <img src={p.thumb} alt="" className="h-full w-full object-cover" referrerPolicy="no-referrer" />
              </button>
            ))}
          </div>
        )}
      </figure>

      {n > 1 && (
        <>
          <button
            onClick={(e) => {
              e.stopPropagation()
              go(-1)
            }}
            aria-label="이전 사진"
            className={`${navBtn} left-2 sm:left-5`}
          >
            <ChevronLeft />
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation()
              go(1)
            }}
            aria-label="다음 사진"
            className={`${navBtn} right-2 sm:right-5`}
          >
            <ChevronRight />
          </button>
        </>
      )}
    </div>
  )
}
