import { useState, useEffect, useRef } from 'react'

interface KnowledgeFile {
  name: string
  size_chars: number
}

interface Props {
  sessionId: string
}

const BASE = import.meta.env.VITE_API_BASE ?? ''

async function apiFetch(path: string, opts?: RequestInit) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? `HTTP ${res.status}`)
  }
  return res.json()
}

export default function KnowledgePage({ sessionId }: Props) {
  const [files, setFiles] = useState<KnowledgeFile[]>([])
  const [totalChars, setTotalChars] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [uploading, setUploading] = useState(false)
  const [pasteMode, setPasteMode] = useState(false)
  const [pasteFilename, setPasteFilename] = useState('')
  const [pasteContent, setPasteContent] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  async function load() {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch(`/knowledge/files?session_id=${sessionId}`)
      setFiles(data.files ?? [])
      setTotalChars(data.total_chars ?? 0)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [sessionId])

  async function importFiles(incoming: Array<{ name: string; content: string }>) {
    setUploading(true)
    setError('')
    setSuccess('')
    try {
      await apiFetch(`/knowledge/import`, {
        method: 'POST',
        body: JSON.stringify({ session_id: sessionId, files: incoming }),
      })
      setSuccess(`Imported ${incoming.length} file${incoming.length > 1 ? 's' : ''}.`)
      await load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setUploading(false)
    }
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(e.target.files ?? [])
    if (!picked.length) return
    const reads = await Promise.all(
      picked.map(
        (f) =>
          new Promise<{ name: string; content: string }>((resolve, reject) => {
            const reader = new FileReader()
            reader.onload = () => resolve({ name: f.name, content: reader.result as string })
            reader.onerror = reject
            reader.readAsText(f)
          })
      )
    )
    await importFiles(reads)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  async function handlePasteImport() {
    if (!pasteFilename.trim() || !pasteContent.trim()) return
    const name = pasteFilename.trim().endsWith('.md') ? pasteFilename.trim() : `${pasteFilename.trim()}.md`
    await importFiles([{ name, content: pasteContent }])
    setPasteFilename('')
    setPasteContent('')
    setPasteMode(false)
  }

  async function handleDelete(name: string) {
    setError('')
    try {
      await apiFetch(`/knowledge/file?session_id=${sessionId}&name=${encodeURIComponent(name)}`, {
        method: 'DELETE',
      })
      setFiles((prev) => prev.filter((f) => f.name !== name))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">📚 Arty Knowledge</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Import markdown files — your AI references them in every conversation.
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setPasteMode((v) => !v)} className="btn-secondary text-sm">
            Paste text
          </button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".md,.txt,.markdown"
            className="hidden"
            onChange={handleFileChange}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="btn-primary text-sm"
          >
            {uploading ? 'Importing…' : '↑ Import files'}
          </button>
        </div>
      </div>

      {error && (
        <div className="text-red-400 text-xs bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">
          {error}
        </div>
      )}
      {success && (
        <div className="text-emerald-400 text-xs bg-emerald-900/20 border border-emerald-800 rounded-lg px-3 py-2">
          {success}
        </div>
      )}

      {pasteMode && (
        <div className="card space-y-3">
          <h3 className="text-sm font-medium text-slate-300">Paste as markdown</h3>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Filename (without extension)</label>
            <input
              className="input"
              placeholder="e.g. my-notes"
              value={pasteFilename}
              onChange={(e) => setPasteFilename(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Content</label>
            <textarea
              className="input min-h-[140px] resize-y font-mono text-xs"
              placeholder="Paste markdown content…"
              value={pasteContent}
              onChange={(e) => setPasteContent(e.target.value)}
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={handlePasteImport}
              disabled={uploading || !pasteFilename.trim() || !pasteContent.trim()}
              className="btn-primary"
            >
              {uploading ? 'Importing…' : 'Import'}
            </button>
            <button onClick={() => setPasteMode(false)} className="btn-ghost">Cancel</button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-slate-500 text-sm">Loading…</div>
      ) : files.length === 0 ? (
        <div className="text-slate-500 text-sm">
          No knowledge files yet. Import a .md or .txt file to get started.
        </div>
      ) : (
        <>
          <div className="text-xs text-slate-500">
            {files.length} file{files.length !== 1 ? 's' : ''} · {totalChars.toLocaleString()} chars total
          </div>
          <div className="space-y-2">
            {files.map((f) => (
              <div key={f.name} className="card flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-medium text-slate-200 truncate">{f.name}</div>
                  <div className="text-xs text-slate-500">{f.size_chars.toLocaleString()} chars</div>
                </div>
                <button
                  onClick={() => handleDelete(f.name)}
                  className="text-xs text-red-400 hover:text-red-300 shrink-0"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
