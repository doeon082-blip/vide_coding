export type FestivalStatus = '진행중' | '예정' | '완료'

export interface Festival {
  id: number
  fstvl_nm: string
  fstvl_start_date: string
  fstvl_end_date: string
  opar: string
  fstvl_co: string
  rdnmadr: string
  ai_summary: string | null
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
  id: number
  ai_summary: string
  cached: boolean
}
