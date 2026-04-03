import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useChat } from '../../hooks/useChat'
import { useAppStore } from '../../store/appStore'
import { api } from '../../api/client'

interface Props {
  sessionId: string
}

export default function ChatPanel({ sessionId }: Props) {
  const { activeModel, setActiveModel } = useAppStore()
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const { data: modelsData } = useQuery({
    queryKey: ['models', sessionId],
    queryFn: () => api.chat.models(sessionId),
  })

  const models = modelsData?.models ?? []

  // Set default model once loaded
  useEffect(() => {
    if (!activeModel && models.length > 0) {
      const available = models.find((m) => m.available)
      if (available) setActiveModel(available.id)
    }
  }, [models, activeModel, setActiveModel])

  const { messages, streaming, error, send, abort } = useChat(sessionId, activeModel)

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function handleSend() {
    if (!input.trim() || streaming) return
    send(input.trim())
    setInput('')
    textareaRef.current?.focus()
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-surface-border bg-surface-card">
        <span className="text-xs text-slate-400 font-medium">Model</span>
        <select
          value={activeModel}
          onChange={(e) => setActiveModel(e.target.value)}
          className="bg-surface border border-surface-border text-slate-200 text-xs rounded px-2 py-1 flex-1 max-w-[200px]"
        >
          {models.length === 0 && <option value="">Loading…</option>}
          {models.map((m) => (
            <option key={m.id} value={m.id} disabled={!m.available}>
              {m.display}{!m.available ? ' (no key)' : ''}
            </option>
          ))}
        </select>
        <div className="ml-auto flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-xs text-emerald-400">Harness active</span>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-slate-500 text-sm mt-12">
            <div className="text-2xl mb-2">⬡</div>
            <div>Your harness is loaded. Give your AI its orders.</div>
          </div>
        )}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-xl px-4 py-2.5 text-sm whitespace-pre-wrap break-words ${
                msg.role === 'user'
                  ? 'bg-brand text-white'
                  : 'bg-surface-hover text-slate-100 border border-surface-border'
              }`}
            >
              {msg.content || (streaming && msg.role === 'assistant' && (
                <span className="inline-flex gap-1">
                  <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:0ms]" />
                  <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:150ms]" />
                  <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:300ms]" />
                </span>
              ))}
              {msg.model && msg.role === 'assistant' && (
                <div className="text-xs text-slate-500 mt-1">{msg.model}</div>
              )}
            </div>
          </div>
        ))}
        {error && (
          <div className="text-red-400 text-xs text-center">{error}</div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-4 py-3 border-t border-surface-border bg-surface-card flex gap-2">
        <textarea
          ref={textareaRef}
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Give your AI its orders… (Enter to send)"
          className="input resize-none flex-1 max-h-32 overflow-y-auto"
          style={{ lineHeight: '1.5' }}
        />
        {streaming ? (
          <button onClick={abort} className="btn-secondary px-3 self-end">
            ■ Stop
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!input.trim() || !activeModel}
            className="btn-primary px-4 self-end"
          >
            Send
          </button>
        )}
      </div>
    </div>
  )
}
