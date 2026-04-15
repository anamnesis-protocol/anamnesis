import { useState, useCallback, useRef, type Dispatch, type SetStateAction, type MutableRefObject } from 'react'
import { api } from '../api/client'
import { FILE_TOOLS, API_TOOLS, toAnthropicTools } from '../tools/toolDefinitions'
import { executeTool, setSessionId } from '../tools/toolExecutor'

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  model?: string
}

// Internal history entries follow Anthropic multi-content format.
// The Message[] state is simplified for display; history is the full record.
type HistoryEntry =
  | { role: 'user'; content: string | Array<{ type: 'tool_result'; tool_use_id: string; content: string; is_error?: boolean }> }
  | { role: 'assistant'; content: string | Array<{ type: 'text'; text: string } | { type: 'tool_use'; id: string; name: string; input: Record<string, unknown> }> }

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

      // Build simple history for the outgoing request (prior display messages).
      const simpleHistory: HistoryEntry[] = messages
        .filter((m) => m.role !== 'assistant' || m.content)
        .map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content }))

      abortRef.current = new AbortController()

      // Set session ID for API tool execution
      setSessionId(sessionId)

      // Combine FILE_TOOLS (Tauri) and API_TOOLS (backend)
      const allTools = [...FILE_TOOLS, ...API_TOOLS]
      const anthropicTools = toAnthropicTools(allTools)

      try {
        await runAgentLoop(
          sessionId,
          text,
          model,
          simpleHistory,
          anthropicTools,
          assistantId,
          setMessages,
          abortRef
        )
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

// ---------------------------------------------------------------------------
// Agentic loop — handles tool_use events, executes locally, continues.
// ---------------------------------------------------------------------------

async function runAgentLoop(
  sessionId: string,
  userMessage: string,
  model: string,
  history: HistoryEntry[],
  tools: unknown[],
  assistantId: string,
  setMessages: Dispatch<SetStateAction<Message[]>>,
  abortRef: MutableRefObject<AbortController | null>
) {
  // History grows as the loop iterates (user turn → assistant turn → tool results → next assistant turn).
  const localHistory: HistoryEntry[] = [...history]
  let currentUserMessage = userMessage
  let isFirstTurn = true
  let toolCallCount = 0
  const MAX_TOOL_CALLS = 20  // safety cap

  while (toolCallCount < MAX_TOOL_CALLS) {
    const res = await api.chat.streamMessage(
      sessionId,
      isFirstTurn ? currentUserMessage : '',
      model,
      localHistory as Array<{ role: string; content: unknown }>,
      tools,
      true // enable_tools for backend API tools
    )

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail ?? `HTTP ${res.status}`)
    }
    if (!res.body) throw new Error('No response body')

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    // Accumulate the full assistant message for this turn.
    let assistantText = ''
    const toolCalls: Array<{ id: string; name: string; input: Record<string, unknown> }> = []

    // SSE parse loop.
    outer: while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const chunk = JSON.parse(line.slice(6))

          if (chunk.type === 'done') {
            break outer
          }

          if (chunk.content) {
            assistantText += chunk.content
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, content: assistantText } : m
              )
            )
          }

          if (chunk.type === 'tool_use') {
            toolCalls.push({
              id: chunk.id,
              name: chunk.name,
              input: chunk.input ?? {},
            })
          }
        } catch {
          // malformed chunk — skip
        }
      }
    }

    if (toolCalls.length === 0) {
      // No tool calls — conversation turn is complete.
      break
    }

    // Append assistant turn to local history (Anthropic content-array format).
    const assistantContent: Array<{ type: 'text'; text: string } | { type: 'tool_use'; id: string; name: string; input: Record<string, unknown> }> = []
    if (assistantText) assistantContent.push({ type: 'text', text: assistantText })
    for (const tc of toolCalls) {
      assistantContent.push({ type: 'tool_use', id: tc.id, name: tc.name, input: tc.input })
    }
    localHistory.push({ role: 'assistant', content: assistantContent })

    // Show tool activity in the assistant bubble.
    const toolLines = toolCalls.map((tc) => `\n\n*[Tool: ${tc.name}]*`).join('')
    setMessages((prev) =>
      prev.map((m) =>
        m.id === assistantId ? { ...m, content: assistantText + toolLines } : m
      )
    )

    // Execute all tool calls in parallel.
    const toolResults = await Promise.all(
      toolCalls.map(async (tc) => {
        const result = await executeTool(tc.name, tc.input)
        return {
          type: 'tool_result' as const,
          tool_use_id: tc.id,
          content: result.content,
          is_error: result.is_error,
        }
      })
    )

    // Append tool results as a user turn.
    localHistory.push({ role: 'user', content: toolResults })

    toolCallCount += toolCalls.length
    isFirstTurn = false
    currentUserMessage = ''
  }
}
