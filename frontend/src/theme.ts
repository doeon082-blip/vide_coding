/** 축제명에서 테마를 추정해 이모지 + 그라데이션 커버를 만든다. (사진이 없을 때의 대체 비주얼) */
export interface FestivalTheme {
  emoji: string
  label: string
  /** Tailwind 클래스는 정적 문자열이어야 빌드에 포함된다 */
  gradient: string
}

const THEMES: { re: RegExp; theme: FestivalTheme }[] = [
  { re: /해맞이|일출|새해|신년/, theme: { emoji: '🌅', label: '해맞이', gradient: 'from-orange-300 to-rose-400' } },
  { re: /벚꽃|꽃|장미|튤립|국화|코스모스|매화|유채|철쭉|연꽃|수국|해바라기|꽃길/, theme: { emoji: '🌸', label: '꽃', gradient: 'from-pink-300 to-rose-400' } },
  { re: /불꽃|야경|빛|등불|유등|루미|조명|등축제|랜턴/, theme: { emoji: '🎆', label: '빛·불꽃', gradient: 'from-indigo-400 to-violet-600' } },
  { re: /음악|콘서트|재즈|뮤직|가요|오케스트라|밴드|록|페스티벌/, theme: { emoji: '🎵', label: '음악', gradient: 'from-violet-400 to-fuchsia-500' } },
  { re: /산천어|얼음|눈꽃|눈|빙|스키|겨울|설/, theme: { emoji: '❄️', label: '겨울', gradient: 'from-sky-300 to-blue-500' } },
  { re: /머드|갯벌|바다|해변|해수욕|수산|물|강|호수|해양|항구|포구|낚시/, theme: { emoji: '🌊', label: '물·바다', gradient: 'from-cyan-300 to-blue-500' } },
  { re: /먹거리|음식|맛|김치|막걸리|한우|치킨|맥주|커피|딸기|사과|쌀|인삼|와인|전통주|고추|굴|새우|젓갈|버섯|차\b|떡|국수/, theme: { emoji: '🍜', label: '먹거리', gradient: 'from-amber-300 to-orange-500' } },
  { re: /나비|곤충|생태|자연|숲|산림|단풍|억새|갈대|습지|공원|정원/, theme: { emoji: '🦋', label: '자연', gradient: 'from-lime-300 to-emerald-500' } },
  { re: /대보름|달집|민속|전통|탈춤|풍물|제전|대제|문화제|역사|왕|성|한옥|국악|농악|단오|줄다리기|제례|향교/, theme: { emoji: '🏮', label: '전통', gradient: 'from-red-400 to-amber-500' } },
  { re: /별|천문|우주/, theme: { emoji: '⭐', label: '별', gradient: 'from-slate-600 to-indigo-700' } },
  { re: /마라톤|걷기|자전거|체육|스포츠|대회|레이싱/, theme: { emoji: '🏃', label: '스포츠', gradient: 'from-teal-300 to-green-500' } },
]

const DEFAULT_THEME: FestivalTheme = { emoji: '🎉', label: '축제', gradient: 'from-teal-300 to-cyan-500' }

export function festivalTheme(name: string): FestivalTheme {
  return THEMES.find((t) => t.re.test(name))?.theme ?? DEFAULT_THEME
}

/** 네이버 이미지 검색 링크 (무료, 새 탭) */
export function imageSearchUrl(name: string): string {
  return `https://search.naver.com/search.naver?where=image&query=${encodeURIComponent(name)}`
}
