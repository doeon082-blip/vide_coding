import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  // GitHub Pages(프로젝트 사이트)는 /<저장소명>/ 아래에서 서비스되므로 워크플로에서 VITE_BASE 지정
  base: process.env.VITE_BASE || '/',
  plugins: [react(), tailwindcss()],
})
