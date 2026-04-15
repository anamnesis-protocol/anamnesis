import { useState, useEffect, useRef } from 'react'

interface DriveFile {
  uuid: string
  filename: string
  size_bytes: number
  mime_type: string
  uploaded_at: string
}

interface Props {
  sessionId: string
}

const BASE = import.meta.env.VITE_API_BASE ?? ''

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / 1024 / 1024).toFixed(1)} MB`
}

export default function DrivePage({ sessionId }: Props) {
  const [files, setFiles] = useState<DriveFile[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  async function load() {
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${BASE}/drive/files?session_id=${sessionId}`)
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        const msg = err.detail ?? `HTTP ${res.status}`
        if (msg.includes('not found') || msg.includes('No drive')) {
          await fetch(`${BASE}/drive/init`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId }),
          })
          setFiles([])
          return
        }
        throw new Error(msg)
      }
      const data = await res.json()
      setFiles(data.files ?? [])
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [sessionId])

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setError('')
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await fetch(`${BASE}/drive/upload?session_id=${sessionId}`, {
        method: 'POST',
        body: fd,
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(err.detail ?? `HTTP ${res.status}`)
      }
      await load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  async function handleDownload(uuid: string, filename: string) {
    try {
      const res = await fetch(`${BASE}/drive/file/${uuid}?session_id=${sessionId}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function handleDelete(uuid: string) {
    try {
      const res = await fetch(`${BASE}/drive/file/${uuid}?session_id=${sessionId}`, { method: 'DELETE' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setFiles((prev) => prev.filter((f) => f.uuid !== uuid))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-100">📁 Arty Drive</h2>
        <div className="flex gap-2">
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            onChange={handleUpload}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="btn-primary text-sm"
          >
            {uploading ? 'Uploading…' : '↑ Upload'}
          </button>
        </div>
      </div>

      {error && (
        <div className="text-red-400 text-xs bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-slate-500 text-sm">Loading…</div>
      ) : files.length === 0 ? (
        <div className="text-slate-500 text-sm">No files yet. Upload a file to get started.</div>
      ) : (
        <div className="space-y-2">
          {files.map((f) => (
            <div key={f.uuid} className="card flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="font-medium text-slate-200 truncate">{f.filename}</div>
                <div className="text-xs text-slate-500">{formatBytes(f.size_bytes)} · {f.mime_type}</div>
              </div>
              <div className="flex gap-2 shrink-0">
                <button
                  onClick={() => handleDownload(f.uuid, f.filename)}
                  className="text-xs text-slate-400 hover:text-slate-200"
                >
                  Download
                </button>
                <button
                  onClick={() => handleDelete(f.uuid)}
                  className="text-xs text-red-400 hover:text-red-300"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
