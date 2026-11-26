import { CalendarDays, History, MapPin, MessageCircle, Send, ShieldCheck, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { sendChat } from './api'
import { StatusBadge } from './components'
import { checkInput, RequestGuard } from './security'
import type { ChatPick } from './types'

type Msg =
  | { role: 'user'; text: string }
  | { role: 'bot'; text: string; picks: ChatPick[]; notes: string[]; suggestions: string[] }

const WELCOME: Msg = {
  role: 'bot',
  text: '안녕하세요, 축제 요정이에요 🧚 “단풍 보고 싶어”, “이번 주말에 갈 만한 축제”처럼 편하게 물어보세요!',
  picks: [],
  notes: [],
  suggestions: ['단풍 보고 싶어', '이번 주말에 갈 만한 축제', '아이랑 체험하기 좋은 축제', '야경이 예쁜 축제', '🎲 아무거나 추천해줘'],
}

function PickCard({ pick, onOpen }: { pick: ChatPick; onOpen: (name: string) => void }) {
  const f = pick.festival
  return (
    <div className="rounded-box border border-base-300 bg-base-100 p-3 text-left text-sm">
      <div className="flex items-start justify-between gap-2">
        <p className="font-bold leading-snug">{f.fstvl_nm}</p>
        <StatusBadge status={f.status} />
      </div>
      {pick.kind === 'past' && (
        <span className="badge badge-warning badge-sm mt-1 gap-1">
          <History size={11} aria-hidden /> 지난 개최 (참고용)
        </span>
      )}
      <p className="mt-1 flex items-center gap-1.5 text-xs opacity-80">
        <CalendarDays size={12} aria-hidden /> {f.fstvl_start_date} ~ {f.fstvl_end_date}
      </p>
      {(f.opar || f.rdnmadr) && (
        <p className="mt-0.5 flex items-start gap-1.5 text-xs opacity-70">
          <MapPin size={12} aria-hidden className="mt-0.5 shrink-0" /> {f.opar || f.rdnmadr}
        </p>
      )}
      <p className="mt-2 leading-relaxed">{pick.reason}</p>
      <div className="mt-2 flex flex-wrap items-center gap-1">
        {pick.evidence.map((e) => (
          <span key={e} className="badge badge-ghost badge-sm" title="이 축제를 고른 근거 (데이터 원문에서 찾은 단어)">
            근거: {e}
          </span>
        ))}
        <span className="badge badge-outline badge-sm opacity-60" title="AI가 쓴 문장은 원문과 대조 검증을 통과해야 쓰이고, 아니면 근거 기반 문장으로 대체돼요">
          {pick.ai_written ? 'AI 문장·검증됨' : '근거 기반 문장'}
        </span>
      </div>
      <button onClick={() => onOpen(f.fstvl_nm)} className="btn btn-xs btn-primary btn-outline mt-2">
        목록에서 자세히 보기
      </button>
    </div>
  )
}

/** 근거 기반 RAG 챗봇. 축제명·일정·장소는 서버가 DB 값을 그대로 내려주고, AI는 추천 이유만 쓴다. */
export function ChatWidget({ onOpenFestival }: { onOpenFestival: (name: string) => void }) {
  const [open, setOpen] = useState(false)
  const [msgs, setMsgs] = useState<Msg[]>([WELCOME])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [warn, setWarn] = useState<string | null>(null)
  const guard = useRef(new RequestGuard(8, 60_000))
  const shown = useRef<string[]>([])
  const end = useRef<HTMLDivElement>(null)

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [msgs, busy, open])

  async function send(raw: string) {
    const text = raw.trim()
    if (!text || busy) return
    setWarn(null)
    const checked = checkInput(text, true) // 보안 프로토콜: 프롬프트 인젝션 포함 사전 검사 (서버가 최종 방어선)
    if (!checked.ok) {
      guard.current.reportViolation()
      setWarn(checked.message)
      return
    }
    const blocked = guard.current.allow()
    if (blocked) {
      setWarn(blocked)
      return
    }
    const more = /더 보여|다른 거|다른거|또 추천|다른 축제/.test(text)
    const history = msgs
      .filter((m): m is Extract<Msg, { role: 'user' }> => m.role === 'user')
      .slice(-3)
      .map((m) => ({ role: 'user' as const, content: m.text }))
    setMsgs((m) => [...m, { role: 'user', text }])
    setInput('')
    setBusy(true)
    try {
      const r = await sendChat(checked.value, history, more ? shown.current.slice(-40) : [])
      shown.current.push(...r.picks.map((p) => p.festival.id))
      setMsgs((m) => [...m, { role: 'bot', text: r.answer, picks: r.picks, notes: r.notes, suggestions: r.suggestions }])
    } catch (e) {
      setMsgs((m) => [
        ...m,
        { role: 'bot', text: (e as Error).message || '잠시 후 다시 시도해 주세요.', picks: [], notes: [], suggestions: [] },
      ])
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        aria-label="축제 요정 챗봇 열기"
        className="btn btn-primary btn-circle btn-lg fixed bottom-5 right-5 z-40 shadow-xl"
      >
        <MessageCircle />
      </button>
    )
  }

  return (
    <section
      role="dialog"
      aria-label="축제 요정 챗봇"
      className="fixed bottom-0 right-0 z-40 flex h-[min(88vh,40rem)] w-full flex-col overflow-hidden rounded-t-box border border-base-300 bg-base-200 shadow-2xl sm:bottom-5 sm:right-5 sm:w-[26rem] sm:rounded-box"
    >
      <header className="flex items-center gap-2 bg-primary px-4 py-3 text-primary-content">
        <span className="text-xl" aria-hidden>
          🧚
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-bold leading-tight">축제 요정</p>
          <p className="flex items-center gap-1 text-xs opacity-90">
            <ShieldCheck size={12} aria-hidden /> 근거 있는 말만 해요 · 로컬 AI
          </p>
        </div>
        <button onClick={() => setOpen(false)} aria-label="챗봇 닫기" className="btn btn-ghost btn-sm btn-circle">
          <X size={18} />
        </button>
      </header>

      <div className="flex-1 space-y-3 overflow-y-auto p-3" aria-live="polite">
        {msgs.map((m, i) =>
          m.role === 'user' ? (
            <div key={i} className="chat chat-end">
              <div className="chat-bubble chat-bubble-primary max-w-[85%] text-sm">{m.text}</div>
            </div>
          ) : (
            <div key={i} className="space-y-2">
              <div className="chat chat-start">
                <div className="chat-bubble max-w-[92%] whitespace-pre-line text-sm leading-relaxed">{m.text}</div>
              </div>
              {m.picks.map((p) => (
                <PickCard key={p.festival.id} pick={p} onOpen={(n) => onOpenFestival(n)} />
              ))}
              {m.notes.map((n) => (
                <div key={n} role="note" className="alert alert-soft alert-warning py-2 text-xs leading-relaxed">
                  {n}
                </div>
              ))}
              {i === msgs.length - 1 && m.suggestions.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {m.suggestions.map((s) => (
                    <button key={s} onClick={() => void send(s)} disabled={busy} className="btn btn-xs btn-soft btn-primary rounded-full">
                      {s}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ),
        )}
        {busy && (
          <div className="chat chat-start">
            <div className="chat-bubble text-sm">
              <span className="loading loading-dots loading-sm" /> 근거를 찾는 중…
            </div>
          </div>
        )}
        <div ref={end} />
      </div>

      {warn && (
        <p role="alert" className="bg-warning/20 px-3 py-1.5 text-xs font-medium text-warning-content">
          {warn}
        </p>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault()
          void send(input)
        }}
        className="join w-full border-t border-base-300 bg-base-100 p-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          maxLength={200}
          placeholder="예: 단풍 보고 싶어"
          aria-label="챗봇에게 질문"
          className="input input-sm join-item flex-1"
        />
        <button disabled={busy || !input.trim()} aria-label="보내기" className="btn btn-primary btn-sm join-item">
          <Send size={14} />
        </button>
      </form>
      <p className="bg-base-100 px-3 pb-2 text-[11px] leading-snug opacity-60">
        축제명·일정·장소는 공공데이터 그대로예요. AI는 추천 이유만 쓰고, 데이터에 없는 내용(가격·주차 등)은 “없어요”라고 답해요.
      </p>
    </section>
  )
}
