import { useEffect, useState } from 'react'
import { isSafeImageUrl } from './security'

/** 무료 이미지 소스: Wikimedia Commons(키 불필요, CORS 허용). 결과가 없으면 picsum 임의 이미지로 대체. */
const COMMONS = 'https://commons.wikimedia.org/w/api.php'
const cache = new Map<string, Promise<string[]>>()

export const fallbackPhotos = (seed: string, n: number) =>
  Array.from({ length: n }, (_, i) => `https://picsum.photos/seed/${seed.slice(0, 12)}-${i}/400/300`)

/** "제23회 2026 광주 추억의 충장축제" → "광주 추억의 충장축제" */
function searchTerm(name: string) {
  return name
    .replace(/제?\s*\d+\s*회/g, ' ')
    .replace(/\b20\d{2}\s*년?/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

async function queryCommons(name: string, limit: number): Promise<string[]> {
  const params = new URLSearchParams({
    action: 'query',
    format: 'json',
    origin: '*',
    generator: 'search',
    gsrsearch: searchTerm(name),
    gsrnamespace: '6',
    gsrlimit: String(limit * 2),
    prop: 'imageinfo',
    iiprop: 'url|mime',
    iiurlwidth: '400',
  })
  try {
    const res = await fetch(`${COMMONS}?${params}`)
    if (!res.ok) return []
    const json = await res.json()
    const pages = Object.values(json?.query?.pages ?? {}) as {
      imageinfo?: { thumburl?: string; mime?: string }[]
    }[]
    return pages
      .map((p) => p.imageinfo?.[0])
      .filter((i) => i && /^image\/(jpeg|png)$/.test(i.mime ?? '') && i.thumburl)
      .map((i) => i!.thumburl!)
      .filter(isSafeImageUrl)
      .slice(0, limit)
  } catch {
    return []
  }
}

export function fetchPhotos(name: string, limit: number): Promise<string[]> {
  const key = `${name}|${limit}`
  if (!cache.has(key)) cache.set(key, queryCommons(name, limit))
  return cache.get(key)!
}

/** 축제별 사진 목록. 로딩 중에는 null, 실제 사진이 없으면 picsum 대체 이미지와 real=false. */
export function usePhotos(id: string, name: string, limit: number, enabled = true) {
  const [state, setState] = useState<{ urls: string[]; real: boolean } | null>(null)
  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    fetchPhotos(name, limit).then((urls) => {
      if (cancelled) return
      setState(urls.length ? { urls, real: true } : { urls: fallbackPhotos(id, limit), real: false })
    })
    return () => {
      cancelled = true
    }
  }, [id, name, limit, enabled])
  return state
}
