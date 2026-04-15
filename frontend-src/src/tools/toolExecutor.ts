/**
 * toolExecutor.ts — Executes tool calls from the AI.
 *
 * Two execution paths:
 * 1. Tauri tools: Local file system operations (read, write, execute)
 * 2. API tools: Backend operations (Pass, Drive, Mail, Calendar)
 *
 * Tool names correspond to schemas in toolDefinitions.ts.
 */

import { readTextFile, writeTextFile, readDir } from '@tauri-apps/api/fs'
import { Command } from '@tauri-apps/api/shell'
import { open as openDialog } from '@tauri-apps/api/dialog'

export interface ToolResult {
  content: string
  is_error?: boolean
}

// Session ID is injected at runtime by useChat hook
let currentSessionId: string | null = null

export function setSessionId(sessionId: string) {
  currentSessionId = sessionId
}

// ---------------------------------------------------------------------------
// API Tool Handlers (Pass/Drive/Mail/Calendar)
// ---------------------------------------------------------------------------

const BASE = import.meta.env.VITE_API_BASE ?? ''

async function apiCall(method: string, path: string, body?: any): Promise<any> {
  if (!currentSessionId) {
    throw new Error('No session ID set for API tool execution')
  }
  
  const url = `${BASE}${path}${path.includes('?') ? '&' : '?'}session_id=${currentSessionId}`
  const res = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? `HTTP ${res.status}`)
  }
  
  return res.json()
}

async function handleListPasswords(): Promise<ToolResult> {
  try {
    const data = await apiCall('GET', '/pass/entries')
    const entries = data.entries || []
    if (entries.length === 0) return { content: 'No password entries found.' }
    
    const lines = entries.map((e: any) => 
      `- ${e.name}${e.username ? ` (${e.username})` : ''}${e.url ? ` - ${e.url}` : ''} [ID: ${e.entry_id}]`
    )
    return { content: `Password entries:\n${lines.join('\n')}` }
  } catch (e) {
    return { content: `Error listing passwords: ${e instanceof Error ? e.message : String(e)}`, is_error: true }
  }
}

async function handleGetPassword(input: { entry_id: string }): Promise<ToolResult> {
  try {
    const data = await apiCall('GET', `/pass/entry/${input.entry_id}`)
    return { content: `Password: ${data.password}` }
  } catch (e) {
    return { content: `Error getting password: ${e instanceof Error ? e.message : String(e)}`, is_error: true }
  }
}

async function handleCreatePassword(input: { name: string; username?: string; password: string; url?: string; notes?: string }): Promise<ToolResult> {
  try {
    await apiCall('POST', '/pass/entry', { ...input, session_id: currentSessionId })
    return { content: `Password entry created: ${input.name}` }
  } catch (e) {
    return { content: `Error creating password: ${e instanceof Error ? e.message : String(e)}`, is_error: true }
  }
}

async function handleListNotes(): Promise<ToolResult> {
  try {
    const data = await apiCall('GET', '/pass/notes')
    const notes = data.notes || []
    if (notes.length === 0) return { content: 'No notes found.' }
    
    const lines = notes.map((n: any) => `- ${n.title} (${n.type}) [ID: ${n.id}]`)
    return { content: `Secure notes:\n${lines.join('\n')}` }
  } catch (e) {
    return { content: `Error listing notes: ${e instanceof Error ? e.message : String(e)}`, is_error: true }
  }
}

async function handleGetNote(input: { note_id: string }): Promise<ToolResult> {
  try {
    const data = await apiCall('GET', `/pass/note/${input.note_id}`)
    return { content: `Note: ${data.title}\nType: ${data.type}\nContent: ${JSON.stringify(data.content, null, 2)}` }
  } catch (e) {
    return { content: `Error getting note: ${e instanceof Error ? e.message : String(e)}`, is_error: true }
  }
}

async function handleCreateNote(input: { type: string; title: string; content: string }): Promise<ToolResult> {
  try {
    const contentObj = typeof input.content === 'string' ? JSON.parse(input.content) : input.content
    await apiCall('POST', '/pass/note', { ...input, content: contentObj, session_id: currentSessionId })
    return { content: `Note created: ${input.title}` }
  } catch (e) {
    return { content: `Error creating note: ${e instanceof Error ? e.message : String(e)}`, is_error: true }
  }
}

async function handleListTotp(): Promise<ToolResult> {
  try {
    const data = await apiCall('GET', '/pass/totp')
    const entries = data.entries || []
    if (entries.length === 0) return { content: 'No TOTP entries found.' }
    
    const lines = entries.map((e: any) => `- ${e.name}${e.issuer ? ` (${e.issuer})` : ''} [ID: ${e.id}]`)
    return { content: `TOTP entries:\n${lines.join('\n')}` }
  } catch (e) {
    return { content: `Error listing TOTP: ${e instanceof Error ? e.message : String(e)}`, is_error: true }
  }
}

async function handleGetTotpCode(input: { totp_id: string }): Promise<ToolResult> {
  try {
    const data = await apiCall('GET', `/pass/totp/${input.totp_id}`)
    return { content: `TOTP code: ${data.code} (valid for ${data.remaining}s)` }
  } catch (e) {
    return { content: `Error getting TOTP code: ${e instanceof Error ? e.message : String(e)}`, is_error: true }
  }
}

async function handleListFiles(): Promise<ToolResult> {
  try {
    const data = await apiCall('GET', '/drive/files')
    const files = data.files || []
    if (files.length === 0) return { content: 'No files found.' }
    
    const lines = files.map((f: any) => `- ${f.name} (${f.size} bytes) [ID: ${f.file_id}]`)
    return { content: `Files:\n${lines.join('\n')}` }
  } catch (e) {
    return { content: `Error listing files: ${e instanceof Error ? e.message : String(e)}`, is_error: true }
  }
}

async function handleListMessages(input: { folder: string }): Promise<ToolResult> {
  try {
    const data = await apiCall('GET', `/mail/${input.folder}`)
    const messages = data.messages || []
    if (messages.length === 0) return { content: `No messages in ${input.folder}.` }
    
    const lines = messages.map((m: any) => `- ${m.subject} from ${m.from_token_id} [ID: ${m.message_id}]`)
    return { content: `Messages (${input.folder}):\n${lines.join('\n')}` }
  } catch (e) {
    return { content: `Error listing messages: ${e instanceof Error ? e.message : String(e)}`, is_error: true }
  }
}

async function handleSendMessage(input: { to_token_id: string; subject: string; body: string }): Promise<ToolResult> {
  try {
    await apiCall('POST', '/mail/send', { ...input, session_id: currentSessionId })
    return { content: `Message sent to ${input.to_token_id}` }
  } catch (e) {
    return { content: `Error sending message: ${e instanceof Error ? e.message : String(e)}`, is_error: true }
  }
}

async function handleListEvents(input: { year: string; month: string }): Promise<ToolResult> {
  try {
    const data = await apiCall('GET', `/calendar/events?year=${input.year}&month=${input.month}`)
    const events = data.events || []
    if (events.length === 0) return { content: `No events in ${input.year}-${input.month}.` }
    
    const lines = events.map((e: any) => `- ${e.date}${e.time ? ` ${e.time}` : ''}: ${e.title}`)
    return { content: `Events (${input.year}-${input.month}):\n${lines.join('\n')}` }
  } catch (e) {
    return { content: `Error listing events: ${e instanceof Error ? e.message : String(e)}`, is_error: true }
  }
}

async function handleCreateEvent(input: { title: string; date: string; time?: string; description?: string; color?: string }): Promise<ToolResult> {
  try {
    await apiCall('POST', '/calendar/event', { ...input, session_id: currentSessionId })
    return { content: `Event created: ${input.title} on ${input.date}` }
  } catch (e) {
    return { content: `Error creating event: ${e instanceof Error ? e.message : String(e)}`, is_error: true }
  }
}

// ---------------------------------------------------------------------------
// Individual tool handlers
// ---------------------------------------------------------------------------

async function handleReadFile(input: { path: string }): Promise<ToolResult> {
  try {
    const content = await readTextFile(input.path)
    return { content }
  } catch (e) {
    return { content: `Error reading file: ${e instanceof Error ? e.message : String(e)}`, is_error: true }
  }
}

async function handleWriteFile(input: { path: string; content: string }): Promise<ToolResult> {
  try {
    await writeTextFile(input.path, input.content)
    return { content: `File written: ${input.path}` }
  } catch (e) {
    return { content: `Error writing file: ${e instanceof Error ? e.message : String(e)}`, is_error: true }
  }
}

async function handleListDirectory(input: { path: string }): Promise<ToolResult> {
  try {
    const entries = await readDir(input.path, { recursive: false })
    const lines = entries.map((e) => {
      const type = e.children !== undefined ? 'dir' : 'file'
      return `${type}  ${e.name ?? ''}`
    })
    return { content: lines.join('\n') || '(empty directory)' }
  } catch (e) {
    return { content: `Error listing directory: ${e instanceof Error ? e.message : String(e)}`, is_error: true }
  }
}

async function handleSearchFiles(input: {
  pattern: string
  directory: string
  file_pattern?: string
}): Promise<ToolResult> {
  try {
    // Use shell grep -r. On Windows with Git Bash this works natively.
    const args = ['-r', '--include', input.file_pattern ?? '*', '-n', input.pattern, input.directory]
    const cmd = new Command('grep', args)
    const out = await cmd.execute()
    if (out.code !== 0 && out.stdout === '') {
      return { content: 'No matches found.' }
    }
    return { content: out.stdout.trim() || 'No matches found.' }
  } catch (e) {
    return { content: `Error searching files: ${e instanceof Error ? e.message : String(e)}`, is_error: true }
  }
}

async function handleExecuteCommand(input: { command: string; cwd?: string }): Promise<ToolResult> {
  try {
    const cmd = new Command('bash', ['-c', input.command], {
      cwd: input.cwd,
    })
    const out = await cmd.execute()
    const combined = [out.stdout, out.stderr].filter(Boolean).join('\n')
    if (out.code !== 0) {
      return {
        content: combined || `Process exited with code ${out.code}`,
        is_error: true,
      }
    }
    return { content: combined || '(no output)' }
  } catch (e) {
    return { content: `Error executing command: ${e instanceof Error ? e.message : String(e)}`, is_error: true }
  }
}

async function handleOpenFileDialog(input: { title?: string; filters?: string }): Promise<ToolResult> {
  try {
    const extensions = input.filters
      ? input.filters.split(',').map((s) => s.trim()).filter(Boolean)
      : undefined

    const selected = await openDialog({
      title: input.title ?? 'Select a file',
      multiple: false,
      directory: false,
      filters: extensions ? [{ name: 'Files', extensions }] : undefined,
    })

    if (!selected) return { content: 'No file selected.' }
    const path = Array.isArray(selected) ? selected[0] : selected
    return { content: path }
  } catch (e) {
    return { content: `Error opening file dialog: ${e instanceof Error ? e.message : String(e)}`, is_error: true }
  }
}

async function handleOpenFolderDialog(input: { title?: string }): Promise<ToolResult> {
  try {
    const selected = await openDialog({
      title: input.title ?? 'Select a folder',
      multiple: false,
      directory: true,
    })

    if (!selected) return { content: 'No folder selected.' }
    const path = Array.isArray(selected) ? selected[0] : selected
    return { content: path }
  } catch (e) {
    return { content: `Error opening folder dialog: ${e instanceof Error ? e.message : String(e)}`, is_error: true }
  }
}

// ---------------------------------------------------------------------------
// Dispatch
// ---------------------------------------------------------------------------

export async function executeTool(name: string, input: Record<string, unknown>): Promise<ToolResult> {
  switch (name) {
    // Tauri file system tools
    case 'read_file':
      return handleReadFile(input as { path: string })
    case 'write_file':
      return handleWriteFile(input as { path: string; content: string })
    case 'list_directory':
      return handleListDirectory(input as { path: string })
    case 'search_files':
      return handleSearchFiles(input as { pattern: string; directory: string; file_pattern?: string })
    case 'execute_command':
      return handleExecuteCommand(input as { command: string; cwd?: string })
    case 'open_file_dialog':
      return handleOpenFileDialog(input as { title?: string; filters?: string })
    case 'open_folder_dialog':
      return handleOpenFolderDialog(input as { title?: string })
    
    // API tools (Pass/Drive/Mail/Calendar)
    case 'list_passwords':
      return handleListPasswords()
    case 'get_password':
      return handleGetPassword(input as { entry_id: string })
    case 'create_password':
      return handleCreatePassword(input as any)
    case 'list_notes':
      return handleListNotes()
    case 'get_note':
      return handleGetNote(input as { note_id: string })
    case 'create_note':
      return handleCreateNote(input as any)
    case 'list_totp':
      return handleListTotp()
    case 'get_totp_code':
      return handleGetTotpCode(input as { totp_id: string })
    case 'list_files':
      return handleListFiles()
    case 'list_messages':
      return handleListMessages(input as { folder: string })
    case 'send_message':
      return handleSendMessage(input as any)
    case 'list_events':
      return handleListEvents(input as { year: string; month: string })
    case 'create_event':
      return handleCreateEvent(input as any)
    
    default:
      return { content: `Unknown tool: ${name}`, is_error: true }
  }
}
