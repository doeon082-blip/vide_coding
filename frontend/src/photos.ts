import { useEffect, useState } from 'react'
import { isSafeImageUrl } from './security'

/** 무료 이미지 소스: Wikimedia Commons(키 불필요, CORS 허용). 관련 없는 임의 사진은 쓰지 않는다. */
const COMMONS = 'https://commons.wikimedia.org/w/api.php'
const cache = new Map<string, Promise<string[]>>()

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
      title?: string
      imageinfo?: { thumburl?: string; mime?: string }[]
    }[]
    // 파일명에 축제명 핵심 단어(2자 이상)가 들어 있는 사진만 채택 → 무관한 사진 차단
    const keywords = searchTerm(name)
      .split(' ')
      .filter((w) => w.length >= 2 && !/^(축제|문화제|행사|대회)$/.test(w))
    return pages
      .filter((p) => keywords.some((k) => (p.title ?? '').includes(k)))
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

/** 축제별 실제 사진 목록(파일명이 축제명과 맞는 것만). 로딩 중에는 null, 없으면 빈 배열. */
export function usePhotos(name: string, limit: number, enabled = true) {
  const [urls, setUrls] = useState<string[] | null>(null)
  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    fetchPhotos(name, limit).then((u) => !cancelled && setUrls(u))
    return () => {
      cancelled = true
    }
  }, [name, limit, enabled])
  return urls
}
