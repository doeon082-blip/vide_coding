import { useEffect, useState } from 'react'
import { fetchPhotos } from './api'
import { isSafeImageUrl } from './security'
import type { PhotoResult } from './types'

const cache = new Map<string, Promise<PhotoResult>>()

function load(id: string): Promise<PhotoResult> {
  if (!cache.has(id)) {
    cache.set(
      id,
      fetchPhotos(id)
        .then((r) => ({ ...r, photos: r.photos.filter((p) => isSafeImageUrl(p.url) && isSafeImageUrl(p.thumb)) }))
        .catch(() => ({ kind: 'none', photos: [], region: '', matched_title: '' }) as PhotoResult),
    )
  }
  return cache.get(id)!
}

/** 한국관광공사 TourAPI(백엔드 경유) 사진. 로딩 중에는 null. */
export function usePhotos(id: string, enabled = true) {
  const [data, setData] = useState<PhotoResult | null>(null)
  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    load(id).then((r) => !cancelled && setData(r))
    return () => {
      cancelled = true
    }
  }, [id, enabled])
  return data
}
