import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

// 프로덕션 빌드에만 적용하는 콘텐츠 보안 정책(XSS·데이터 유출 완화).
//  - 스크립트/스타일은 같은 출처만, 이미지는 한국관광공사 도메인만
//  - API는 런타임 설정(config.json)으로 주소가 바뀌므로 https 전체 + 로컬 개발 주소 허용
const CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self'",
  "img-src 'self' data: https://tong.visitkorea.or.kr",
  "connect-src 'self' https: http://localhost:* http://127.0.0.1:*",
  "font-src 'self' data:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join('; ')

const cspPlugin = (): Plugin => ({
  name: 'inject-csp',
  transformIndexHtml(html, ctx) {
    if (ctx.server) return html // dev
    return html.replace('<head>', `<head>\n    <meta http-equiv="Content-Security-Policy" content="${CSP}" />`)
  },
})

// https://vite.dev/config/
export default defineConfig({
  // GitHub Pages(프로젝트 사이트)는 /<저장소명>/ 아래에서 서비스되므로 워크플로에서 VITE_BASE 지정
  base: process.env.VITE_BASE || '/',
  plugins: [react(), tailwindcss(), cspPlugin()],
})
