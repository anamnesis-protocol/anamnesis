import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, SkillSummary } from '../../api/client'

interface Props {
  sessionId: string
}

export default function SkillsPanel({ sessionId }: Props) {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [instructions, setInstructions] = useState('')
  const [tags, setTags] = useState('')
  const [formError, setFormError] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['skills', sessionId],
    queryFn: () => api.skills.list(sessionId),
  })

  const saveMutation = useMutation({
    mutationFn: () =>
      api.skills.upsert(sessionId, {
        name: name.trim(),
        description: description.trim(),
        instructions: instructions.trim(),
        tags: tags.split(',').map((t) => t.trim()).filter(Boolean),
        input_schema: { type: 'object', properties: {} },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['skills', sessionId] })
      setShowForm(false)
      setName(''); setDescription(''); setInstructions(''); setTags('')
    },
    onError: (e: unknown) => setFormError(e instanceof Error ? e.message : String(e)),
  })

  const deleteMutation = useMutation({
    mutationFn: (skill_id: string) => api.skills.delete(skill_id, sessionId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['skills', sessionId] }),
  })

  const skills: SkillSummary[] = data?.skills ?? []

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-surface-border">
        <span className="text-sm font-medium text-slate-200">
          Skills ({skills.length})
        </span>
        <button onClick={() => setShowForm((v) => !v)} className="btn-secondary text-xs">
          {showForm ? '✕ Cancel' : '+ New Skill'}
        </button>
      </div>

      {/* New skill form */}
      {showForm && (
        <div className="p-4 border-b border-surface-border space-y-3 bg-surface-hover">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Name (snake_case)</label>
            <input className="input" placeholder="analyze_contract" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Description</label>
            <input className="input" placeholder="What this skill does" value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Instructions (how to perform this task)</label>
            <textarea
              className="input resize-none text-xs"
              rows={4}
              placeholder="Step-by-step instructions for the AI…"
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Tags (comma-separated)</label>
            <input className="input" placeholder="security, blockchain" value={tags} onChange={(e) => setTags(e.target.value)} />
          </div>
          {formError && <p className="text-red-400 text-xs">{formError}</p>}
          <button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending || !name || !description || !instructions}
            className="btn-primary w-full"
          >
            {saveMutation.isPending ? 'Saving…' : 'Save Skill to Companion'}
          </button>
        </div>
      )}

      {/* Skills list */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && (
          <div className="p-4 text-xs text-slate-500 text-center">Loading skills…</div>
        )}
        {!isLoading && skills.length === 0 && (
          <div className="p-6 text-center">
            <div className="text-2xl mb-2">🧠</div>
            <p className="text-slate-500 text-xs">
              No skills yet. When your AI learns a task, package it here for reuse across sessions.
            </p>
          </div>
        )}
        {skills.map((skill) => (
          <div
            key={skill.id}
            className="px-4 py-3 border-b border-surface-border hover:bg-surface-hover transition-colors"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-slate-200 mono truncate">
                  {skill.name}
                </div>
                <div className="text-xs text-slate-400 mt-0.5 line-clamp-2">
                  {skill.description}
                </div>
                {skill.tags.length > 0 && (
                  <div className="flex gap-1 mt-1.5 flex-wrap">
                    {skill.tags.map((tag) => (
                      <span key={tag} className="badge badge-purple text-xs">{tag}</span>
                    ))}
                  </div>
                )}
              </div>
              <button
                onClick={() => deleteMutation.mutate(skill.id)}
                disabled={deleteMutation.isPending}
                className="btn-ghost text-xs text-red-400 hover:text-red-300 shrink-0"
                title="Remove skill"
              >
                ✕
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
