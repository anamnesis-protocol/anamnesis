import { useState, useEffect } from 'react'

interface Note {
  id: string
  type: 'credit_card' | 'document' | 'custom'
  title: string
  updated_at: string
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

export default function NotesPage({ sessionId }: Props) {
  const [notes, setNotes] = useState<Note[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  // Form state
  const [noteType, setNoteType] = useState<'credit_card' | 'document' | 'custom'>('custom')
  const [title, setTitle] = useState('')
  const [content, setContent] = useState<any>({})
  const [saving, setSaving] = useState(false)
  const [showSensitive, setShowSensitive] = useState<Record<string, boolean>>({})

  async function load() {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch(`/pass/notes?session_id=${sessionId}`)
      setNotes(data.notes ?? [])
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      if (msg.includes('not found') || msg.includes('No notes vault')) {
        try {
          await apiFetch(`/pass/note`, {
            method: 'POST',
            body: JSON.stringify({ action: 'init', session_id: sessionId }),
          })
          setNotes([])
        } catch {
          setError(msg)
        }
      } else {
        setError(msg)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [sessionId])

  async function handleSave() {
    if (!title.trim()) return
    setSaving(true)
    setError('')
    try {
      if (editingId) {
        await apiFetch(`/pass/note/${editingId}?session_id=${sessionId}`, {
          method: 'PATCH',
          body: JSON.stringify({ session_id: sessionId, type: noteType, title, content }),
        })
      } else {
        await apiFetch(`/pass/note`, {
          method: 'POST',
          body: JSON.stringify({ session_id: sessionId, type: noteType, title, content }),
        })
      }
      setTitle('')
      setContent({})
      setShowAdd(false)
      setEditingId(null)
      await load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  async function handleEdit(note: Note) {
    try {
      const data = await apiFetch(`/pass/note/${note.id}?session_id=${sessionId}`)
      setNoteType(data.type)
      setTitle(data.title)
      setContent(data.content)
      setEditingId(note.id)
      setShowAdd(true)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function handleDelete(noteId: string) {
    try {
      await apiFetch(`/pass/note/${noteId}?session_id=${sessionId}`, { method: 'DELETE' })
      setNotes((prev) => prev.filter((n) => n.id !== noteId))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const filtered = notes.filter(n =>
    n.title.toLowerCase().includes(search.toLowerCase())
  )

  const renderForm = () => {
    if (noteType === 'credit_card') {
      return (
        <>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Cardholder name</label>
            <input className="input" value={content.cardholder || ''} onChange={e => setContent({...content, cardholder: e.target.value})} />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Card number</label>
            <input className="input" type={showSensitive['number'] ? 'text' : 'password'} value={content.number || ''} onChange={e => setContent({...content, number: e.target.value})} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Expiry (MM/YY)</label>
              <input className="input" placeholder="12/25" value={content.expiry || ''} onChange={e => setContent({...content, expiry: e.target.value})} />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">CVV</label>
              <input className="input" type={showSensitive['cvv'] ? 'text' : 'password'} value={content.cvv || ''} onChange={e => setContent({...content, cvv: e.target.value})} />
            </div>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">PIN</label>
            <input className="input" type={showSensitive['pin'] ? 'text' : 'password'} value={content.pin || ''} onChange={e => setContent({...content, pin: e.target.value})} />
          </div>
        </>
      )
    } else if (noteType === 'document') {
      return (
        <>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Document type</label>
            <input className="input" placeholder="e.g. Passport, Driver's License" value={content.doc_type || ''} onChange={e => setContent({...content, doc_type: e.target.value})} />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Document number</label>
            <input className="input" type={showSensitive['doc_number'] ? 'text' : 'password'} value={content.doc_number || ''} onChange={e => setContent({...content, doc_number: e.target.value})} />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Issued by</label>
            <input className="input" value={content.issued_by || ''} onChange={e => setContent({...content, issued_by: e.target.value})} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Issue date</label>
              <input className="input" type="date" value={content.issue_date || ''} onChange={e => setContent({...content, issue_date: e.target.value})} />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Expiry date</label>
              <input className="input" type="date" value={content.expiry_date || ''} onChange={e => setContent({...content, expiry_date: e.target.value})} />
            </div>
          </div>
        </>
      )
    } else {
      return (
        <div>
          <label className="block text-xs text-slate-400 mb-1">Content</label>
          <textarea className="input" rows={6} value={content.text || ''} onChange={e => setContent({...content, text: e.target.value})} />
        </div>
      )
    }
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-100">📝 Secure Notes</h2>
        <button onClick={() => { setShowAdd((v) => !v); setEditingId(null); setTitle(''); setContent({}); setNoteType('custom') }} className="btn-primary text-sm">
          {showAdd ? 'Cancel' : '+ Add'}
        </button>
      </div>

      {!showAdd && (
        <div className="relative">
          <input
            type="text"
            placeholder="Search notes…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="input text-sm w-full"
          />
        </div>
      )}

      {error && (
        <div className="text-red-400 text-xs bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {showAdd && (
        <div className="card space-y-3">
          <h3 className="text-sm font-medium text-slate-300">{editingId ? 'Edit note' : 'New note'}</h3>
          
          <div>
            <label className="block text-xs text-slate-400 mb-1">Note type</label>
            <select className="input" value={noteType} onChange={e => setNoteType(e.target.value as any)}>
              <option value="custom">Custom Note</option>
              <option value="credit_card">Credit Card</option>
              <option value="document">Document</option>
            </select>
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Title</label>
            <input className="input" value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. My Visa Card" />
          </div>

          {renderForm()}

          <button onClick={handleSave} disabled={saving || !title.trim()} className="btn-primary w-full">
            {saving ? 'Saving…' : editingId ? 'Update note' : 'Save note'}
          </button>
        </div>
      )}

      {loading ? (
        <div className="text-slate-500 text-sm">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="text-slate-500 text-sm">{search ? 'No notes match.' : 'No notes yet. Add your first note above.'}</div>
      ) : (
        <div className="space-y-2">
          {filtered.map((note) => (
            <div key={note.id} className="card space-y-1">
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-medium text-slate-200">{note.title}</span>
                  <span className="ml-2 text-xs text-slate-500">
                    {note.type === 'credit_card' ? '💳' : note.type === 'document' ? '📄' : '📝'}
                  </span>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => handleEdit(note)} className="text-xs text-slate-400 hover:text-slate-200">
                    Edit
                  </button>
                  <button onClick={() => handleDelete(note.id)} className="text-xs text-red-400 hover:text-red-300">
                    Delete
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
