export type FestivalStatus = '진행중' | '예정' | '완료'

export interface Festival {
  id: string
  fstvl_nm: string
  fstvl_start_date: string
  fstvl_end_date: string
  opar: string
  fstvl_co: string
  rdnmadr: string
  ai_summary: string
  status: FestivalStatus | null
}

export interface FestivalPage {
  total: number
  page: number
  size: number
  total_pages: number
  items: Festival[]
}

export interface SummaryResult {
  id: string
  ai_summary: string
  cached: boolean
}

export interface Photo {
  url: string
  thumb: string
  caption: string
}

export interface PhotoResult {
  kind: 'festival' | 'region' | 'none'
  photos: Photo[]
  region: string
  matched_title: string
}
