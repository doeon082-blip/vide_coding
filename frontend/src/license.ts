/** 한국관광공사 사진의 공공누리(KOGL) 유형 표기 */
export const KOGL_INFO_URL = 'https://www.mcst.go.kr/kor/s_open/kogl/koglType.jsp'

export function koglLabel(license: string): string {
  switch (license) {
    case 'Type1':
      return '공공누리 제1유형 (출처표시)'
    case 'Type3':
      return '공공누리 제3유형 (출처표시·변경금지)'
    case 'Type2':
      return '공공누리 제2유형 (출처표시·상업적 이용금지)'
    case 'Type4':
      return '공공누리 제4유형 (출처표시·상업적 이용금지·변경금지)'
    default:
      return '출처: 한국관광공사'
  }
}

/** 변경금지 유형(제3·4)은 사진을 자르거나 가공하지 않고 원본 비율 그대로 보여줘야 한다 */
export const isNoDerivatives = (license: string) => license === 'Type3' || license === 'Type4'
