import { useState } from 'react'
import { useAppStore } from '../../store/appStore'

const SECTION_LABELS: Record<string, string> = {
  soul: 'Soul Directives',
  user: 'User Profile',
  config: 'AI Configuration',
  session_state: 'Session State',
}

const SECTION_DESCRIPTIONS: Record<string, string> = {
  soul: "Your AI companion's core directives — who it is and how it operates.",
  user: 'Your profile — preferences, background, goals.',
  config: "Your AI's tone, style, and expertise focus.",
  session_state: 'What was worked on and what comes next.',
}

interface Props {
  sessionId: string
}

export default function VaultSections({ sessionId: _sessionId }: Props) {
  const { session, activeSection, setActiveSection, setPendingEdit, pendingEdits } = useAppStore()
  const [editMode, setEditMode] = useState(false)

  if (!session) return null

  const sections = session.sections
  const sectionNames = Object.keys(sections)
  const currentName = activeSection && sections[activeSection] !== undefined ? activeSection : sectionNames[0]
  const rawContent = pendingEdits[currentName] ?? sections[currentName] ?? ''

  function handleEdit(content: string) {
    setPendingEdit(currentName, content)
  }

  const isDirty = Object.keys(pendingEdits).length > 0

  return (
    <div className="flex flex-col h-full">
      {/* Section tabs */}
      <div className="flex border-b border-surface-border overflow-x-auto">
        {sectionNames.map((name) => (
          <button
            key={name}
            onClick={() => { setActiveSection(name); setEditMode(false) }}
            className={`px-3 py-2 text-xs font-medium whitespace-nowrap transition-colors border-b-2 ${
              name === currentName
                ? 'border-brand text-brand'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            {SECTION_LABELS[name] ?? name}
            {pendingEdits[name] !== undefined && (
              <span className="ml-1 w-1.5 h-1.5 rounded-full bg-yellow-400 inline-block" />
            )}
          </button>
        ))}
      </div>

      {/* Section description */}
      <div className="px-4 py-2 border-b border-surface-border bg-surface-card flex items-center justify-between">
        <span className="text-xs text-slate-500">
          {SECTION_DESCRIPTIONS[currentName] ?? currentName}
        </span>
        <div className="flex items-center gap-2">
          {isDirty && (
            <span className="badge badge-yellow text-xs">Unsaved edits</span>
          )}
          <button
            onClick={() => setEditMode((v) => !v)}
            className="btn-ghost text-xs"
          >
            {editMode ? 'Preview' : 'Edit'}
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {editMode ? (
          <textarea
            className="w-full h-full bg-surface text-slate-100 text-xs font-mono p-4 resize-none focus:outline-none"
            value={rawContent}
            onChange={(e) => handleEdit(e.target.value)}
            spellCheck={false}
          />
        ) : (
          <div className="h-full overflow-y-auto p-4">
            <pre className="text-xs text-slate-300 whitespace-pre-wrap font-mono leading-relaxed">
              {rawContent || <span className="text-slate-600 italic">Empty section</span>}
            </pre>
          </div>
        )}
      </div>
    </div>
  )
}
