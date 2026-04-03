import { useState, useCallback, useRef } from 'react'
import { api } from '../api/client'

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  model?: string
}

export function useChat(sessionId: string, model: string) {
  const [messages, setMessages] = useState<Message[]>([])
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState('')
  const abortRef = useRef<AbortController | null>(null)

  const send = useCallback(
    async (text: string) => {
      if (!text.trim() || streaming) return

      const userMsg: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content: text,
      }

      const assistantId = crypto.randomUUID()
      const assistantMsg: Message = {
        id: assistantId,
        role: 'assistant',
        content: '',
        model,
      }

      setMessages((prev) => [...prev, userMsg, assistantMsg])
      setStreaming(true)
      setError('')

      const history = messages
        .filter((m) => m.role !== 'assistant' || m.content)
        .map((m) => ({ role: m.role, content: m.content }))

      abortRef.current = new AbortController()

      try {
        const res = await api.chat.streamMessage(sessionId, text, model, history)
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }))
          throw new Error(err.detail ?? `HTTP ${res.status}`)
        }
        if (!res.body) throw new Error('No response body')

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            try {
              const chunk = JSON.parse(line.slice(6))
              if (chunk.content) {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId ? { ...m, content: m.content + chunk.content } : m
                  )
                )
              }
            } catch {
              // malformed chunk — skip
            }
          }
        }
      } catch (e: unknown) {
        if (e instanceof Error && e.name === 'AbortError') return
        const msg = e instanceof Error ? e.message : String(e)
        setError(msg)
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: `[Error: ${msg}]` }
              : m
          )
        )
      } finally {
        setStreaming(false)
      }
    },
    [messages, model, sessionId, streaming]
  )

  const abort = useCallback(() => {
    abortRef.current?.abort()
    setStreaming(false)
  }, [])

  return { messages, streaming, error, send, abort }
}
