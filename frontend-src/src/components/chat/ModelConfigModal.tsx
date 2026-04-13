import { useState } from 'react'
import { api } from '../../api/client'

interface Props {
  sessionId: string
  onClose: () => void
  onSaved: () => void
}

const PROVIDERS = [
  { id: 'anthropic', label: 'Anthropic', placeholder: 'sk-ant-api03-...' },
  { id: 'openai', label: 'OpenAI', placeholder: 'sk-...' },
  { id: 'openrouter', label: 'OpenRouter (100+ models)', placeholder: 'sk-or-v1-...' },
  { id: 'google', label: 'Google (Gemini)', placeholder: 'AIza...' },
  { id: 'mistral', label: 'Mistral', placeholder: 'your-mistral-key' },
  { id: 'groq', label: 'Groq', placeholder: 'gsk_...' },
]

export default function ModelConfigModal({ sessionId, onClose, onSaved }: Props) {
  const [keys, setKeys] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function handleSave() {
    const toSave = Object.fromEntries(
      Object.entries(keys).filter(([, v]) => v.trim())
    )
    if (Object.keys(toSave).length === 0) {
      setError('Enter at least one API key.')
      return
    }
    setSaving(true)
    setError('')
    try {
      await api.chat.setKeys(sessionId, toSave)
      onSaved()
      onClose()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-md space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-slate-100 font-semibold">Configure AI Models</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-lg leading-none">×</button>
        </div>

        <p className="text-xs text-slate-400">
          Keys are stored in your session only — never persisted to disk or shared.
          Cleared when your vault session closes.
        </p>

        <div className="space-y-3">
          {PROVIDERS.map((p) => (
            <div key={p.id}>
              <label className="block text-xs text-slate-400 mb-1">{p.label}</label>
              <input
                type="password"
                className="input mono text-xs"
                placeholder={p.placeholder}
                value={keys[p.id] ?? ''}
                onChange={(e) => setKeys((prev) => ({ ...prev, [p.id]: e.target.value }))}
              />
            </div>
          ))}
        </div>

        {error && (
          <div className="text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">
            {error}
          </div>
        )}

        <div className="flex gap-2">
          <button onClick={onClose} className="btn-ghost flex-1 text-sm">Cancel</button>
          <button onClick={handleSave} disabled={saving} className="btn-primary flex-1 text-sm">
            {saving ? 'Saving…' : 'Save Keys'}
          </button>
        </div>
      </div>
    </div>
  )
}
