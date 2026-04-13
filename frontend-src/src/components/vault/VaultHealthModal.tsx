import { useState, useEffect, useCallback } from 'react'
import { api, VaultHealthResponse, HealthStatus, VaultOverall } from '../../api/client'

interface Props {
  sessionId: string
  onClose: () => void
}

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------

function statusColor(s: HealthStatus | VaultOverall): string {
  if (s === 'pass' || s === 'healthy') return 'text-emerald-400'
  if (s === 'warn' || s === 'degraded') return 'text-amber-400'
  if (s === 'critical') return 'text-red-400'
  return 'text-slate-500'
}

function statusBg(s: HealthStatus | VaultOverall): string {
  if (s === 'pass' || s === 'healthy') return 'bg-emerald-900/30 border-emerald-800'
  if (s === 'warn' || s === 'degraded') return 'bg-amber-900/30 border-amber-800'
  if (s === 'critical') return 'bg-red-900/30 border-red-800'
  return 'bg-slate-800 border-slate-700'
}

function statusIcon(s: HealthStatus | VaultOverall): string {
  if (s === 'pass' || s === 'healthy') return '✓'
  if (s === 'warn' || s === 'degraded') return '⚠'
  if (s === 'critical') return '✗'
  return '–'
}

function overallLabel(s: VaultOverall): string {
  if (s === 'healthy') return 'Companion Healthy'
  if (s === 'degraded') return 'Companion Degraded'
  return 'Companion Critical'
}

function passCount(checks: VaultHealthResponse['checks']): number {
  return Object.values(checks).filter(c => c.status === 'pass').length
}

// ---------------------------------------------------------------------------
// Check row — collapsible
// ---------------------------------------------------------------------------

interface CheckRowProps {
  label: string
  status: HealthStatus
  summary: string
  children?: React.ReactNode
}

function CheckRow({ label, status, summary, children }: CheckRowProps) {
  const [open, setOpen] = useState(false)
  const hasDetail = !!children

  return (
    <div className={`rounded border ${statusBg(status)} overflow-hidden`}>
      <button
        className="w-full flex items-center gap-3 px-3 py-2.5 text-left"
        onClick={() => hasDetail && setOpen(o => !o)}
        disabled={!hasDetail}
      >
        <span className={`font-mono font-bold text-sm w-4 shrink-0 ${statusColor(status)}`}>
          {statusIcon(status)}
        </span>
        <span className="text-slate-200 text-xs font-medium w-40 shrink-0">{label}</span>
        <span className="text-slate-400 text-xs flex-1 truncate">{summary}</span>
        {hasDetail && (
          <span className="text-slate-600 text-xs ml-2">{open ? '▲' : '▼'}</span>
        )}
      </button>

      {open && children && (
        <div className="px-4 pb-3 pt-0.5 border-t border-slate-700/60 text-xs text-slate-400 space-y-1.5">
          {children}
        </div>
      )}
    </div>
  )
}

function DetailLine({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div className="flex gap-2">
      <span className="text-slate-500 shrink-0">{label}:</span>
      <span className="text-slate-300 font-mono">{value ?? '—'}</span>
    </div>
  )
}

function IssueList({ items }: { items: Array<{ section: string; issues: string[] }> }) {
  if (!items.length) return <span className="text-emerald-400">No issues.</span>
  return (
    <ul className="space-y-1">
      {items.map((item, i) => (
        <li key={i}>
          <span className="text-slate-300 font-mono">{item.section}</span>
          <ul className="ml-3 mt-0.5 space-y-0.5">
            {item.issues.map((issue, j) => (
              <li key={j} className="text-amber-300">• {issue}</li>
            ))}
          </ul>
        </li>
      ))}
    </ul>
  )
}

// ---------------------------------------------------------------------------
// Main modal
// ---------------------------------------------------------------------------

export default function VaultHealthModal({ sessionId, onClose }: Props) {
  const [health, setHealth] = useState<VaultHealthResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [repairing, setRepairing] = useState(false)
  const [repairResult, setRepairResult] = useState<string | null>(null)
  const [error, setError] = useState('')

  const fetchHealth = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await api.vault.health(sessionId)
      setHealth(data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  const handleRepair = useCallback(async () => {
    setRepairing(true)
    setRepairResult(null)
    setError('')
    try {
      const result = await api.vault.repair(sessionId)
      const notes = result.repairs.map((r: Record<string, unknown>) => r.note).filter(Boolean).join(' | ')
      setRepairResult(
        `${result.fixed} fixed, ${result.improved} improved, ${result.failed} failed${notes ? ' — ' + notes : ''}`
      )
      await fetchHealth()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setRepairing(false)
    }
  }, [sessionId, fetchHealth])

  useEffect(() => { fetchHealth() }, [fetchHealth])

  const c = health?.checks

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-xl max-h-[90vh] flex flex-col">

        {/* Header */}
        <div className="flex items-center justify-between mb-4 shrink-0">
          <h2 className="text-slate-100 font-semibold">Companion Health</h2>
          <div className="flex items-center gap-2">
            {health && health.overall !== 'healthy' && (
              <button
                onClick={handleRepair}
                disabled={repairing || loading}
                className="text-xs text-amber-300 hover:text-amber-100 border border-amber-800 bg-amber-900/20 rounded px-2 py-1 disabled:opacity-40"
              >
                {repairing ? 'Repairing…' : 'Auto-Repair'}
              </button>
            )}
            <button
              onClick={fetchHealth}
              disabled={loading || repairing}
              className="text-xs text-slate-400 hover:text-slate-200 border border-slate-700 rounded px-2 py-1 disabled:opacity-40"
            >
              {loading ? 'Checking…' : 'Refresh'}
            </button>
            <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-lg leading-none">×</button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2 mb-3 shrink-0">
            {error}
          </div>
        )}

        {/* Repair result */}
        {repairResult && (
          <div className="text-emerald-300 text-xs bg-emerald-900/20 border border-emerald-800 rounded px-3 py-2 mb-3 shrink-0">
            Repair complete — {repairResult}
          </div>
        )}

        {/* Loading */}
        {loading && !health && (
          <div className="flex items-center justify-center py-12">
            <div className="w-5 h-5 border-2 border-brand border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {/* Overall banner */}
        {health && !loading && (
          <>
            <div className={`rounded border px-4 py-3 mb-4 flex items-center gap-3 shrink-0 ${statusBg(health.overall)}`}>
              <span className={`text-xl font-bold ${statusColor(health.overall)}`}>
                {statusIcon(health.overall)}
              </span>
              <div className="flex-1">
                <div className={`font-semibold text-sm ${statusColor(health.overall)}`}>
                  {overallLabel(health.overall)}
                </div>
                <div className="text-xs text-slate-400 mt-0.5">
                  {passCount(health.checks)}/9 checks passed
                  &nbsp;·&nbsp;
                  <span className="mono">{health.token_id}</span>
                  &nbsp;·&nbsp;
                  {health.sections_loaded.length} sections loaded
                </div>
              </div>
            </div>

            {/* Check list */}
            <div className="overflow-y-auto flex-1 space-y-1.5 pr-1">

              {/* Completeness */}
              <CheckRow
                label="Completeness"
                status={c!.completeness.status}
                summary={
                  c!.completeness.sections_missing.length
                    ? `Missing: ${c!.completeness.sections_missing.join(', ')}`
                    : c!.completeness.sections_empty.length
                    ? `Empty: ${c!.completeness.sections_empty.join(', ')}`
                    : `All ${c!.completeness.sections_present.length} sections present`
                }
              >
                <DetailLine label="Present" value={c!.completeness.sections_present.join(', ')} />
                {c!.completeness.sections_missing.length > 0 && (
                  <DetailLine label="Missing" value={c!.completeness.sections_missing.join(', ')} />
                )}
                {c!.completeness.sections_empty.length > 0 && (
                  <DetailLine label="Empty" value={c!.completeness.sections_empty.join(', ')} />
                )}
              </CheckRow>

              {/* Size */}
              <CheckRow
                label="Section Size"
                status={c!.size.status}
                summary={
                  c!.size.sections.some(s => s.issue)
                    ? c!.size.sections.filter(s => s.issue).map(s => s.section).join(', ') + ' — see details'
                    : 'All sections within limits'
                }
              >
                {c!.size.sections.map(s => (
                  <div key={s.section} className="flex gap-2 items-baseline">
                    <span className="text-slate-300 font-mono w-28 shrink-0">{s.section}</span>
                    <span>{s.chars.toLocaleString()} chars (~{s.tokens_estimate.toLocaleString()} tokens)</span>
                    {s.issue && <span className="text-amber-300 ml-1">— {s.issue}</span>}
                  </div>
                ))}
              </CheckRow>

              {/* Structure */}
              <CheckRow
                label="Structure"
                status={c!.structure.status}
                summary={
                  c!.structure.issues.length
                    ? `${c!.structure.issues.length} section(s) need headers`
                    : 'All sections have markdown structure'
                }
              >
                <IssueList items={c!.structure.issues} />
              </CheckRow>

              {/* Staleness */}
              <CheckRow
                label="Staleness"
                status={c!.staleness.status}
                summary={c!.staleness.note}
              >
                <DetailLine label="Last date found" value={c!.staleness.last_date} />
                <DetailLine label="Days since update" value={c!.staleness.days_since_update} />
                <DetailLine label="Warn after" value={`${c!.staleness.warn_threshold_days} days`} />
                <DetailLine label="Critical after" value={`${c!.staleness.critical_threshold_days} days`} />
              </CheckRow>

              {/* Metadata */}
              <CheckRow
                label="Metadata"
                status={c!.metadata.status}
                summary={
                  c!.metadata.issues.length
                    ? `${c!.metadata.issues.length} section(s) missing expected fields`
                    : 'All sections have required fields'
                }
              >
                <IssueList items={c!.metadata.issues} />
              </CheckRow>

              {/* Duplicate content */}
              <CheckRow
                label="Duplicate Content"
                status={c!.duplicate_content.status}
                summary={c!.duplicate_content.note}
              >
                {c!.duplicate_content.duplicates.length > 0 ? (
                  <ul className="space-y-2">
                    {c!.duplicate_content.duplicates.map((d, i) => (
                      <li key={i}>
                        <span className="text-amber-300">Sections: {d.sections.join(' + ')}</span>
                        <div className="text-slate-500 mt-0.5 font-mono text-[10px] truncate">
                          "{d.preview}"
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <span className="text-emerald-400">No duplicate paragraphs detected.</span>
                )}
              </CheckRow>

              {/* RAG index */}
              <CheckRow
                label="RAG Index"
                status={c!.rag_index.status}
                summary={c!.rag_index.note}
              >
                <DetailLine label="Chunks indexed" value={c!.rag_index.chunks} />
                <DetailLine label="Avg chunk size" value={`${c!.rag_index.avg_chars_per_chunk} chars`} />
                {c!.rag_index.tiny_chunks > 0 && (
                  <DetailLine label="Too small (<50 chars)" value={c!.rag_index.tiny_chunks} />
                )}
                {c!.rag_index.oversized_chunks > 0 && (
                  <DetailLine label="Oversized (>1200 chars)" value={c!.rag_index.oversized_chunks} />
                )}
                <p className="text-slate-500 mt-1">
                  Ideal range: 150–800 chars per chunk. Add markdown headers to break up large sections.
                </p>
              </CheckRow>

              {/* Session state growth */}
              <CheckRow
                label="State Growth"
                status={c!.session_state_growth.status}
                summary={c!.session_state_growth.note}
              >
                <DetailLine label="Current size" value={`${c!.session_state_growth.chars.toLocaleString()} chars (~${c!.session_state_growth.tokens_estimate.toLocaleString()} tokens)`} />
                <DetailLine label="Warn at" value={`${c!.session_state_growth.warn_threshold_chars.toLocaleString()} chars`} />
                <DetailLine label="Critical at" value={`${c!.session_state_growth.critical_threshold_chars.toLocaleString()} chars`} />
                <p className="text-slate-500 mt-1">
                  session_state is auto-updated on every close. Condense older entries to keep it lean.
                </p>
              </CheckRow>

              {/* HFS registry */}
              <CheckRow
                label="HFS Registry"
                status={c!.hfs_registry.status}
                summary={
                  c!.hfs_registry.unregistered_sections.length
                    ? `${c!.hfs_registry.unregistered_sections.length} section(s) not in vault index`
                    : `${c!.hfs_registry.registered_sections.length} sections registered on-chain`
                }
              >
                <DetailLine label="Registered" value={c!.hfs_registry.registered_sections.join(', ')} />
                {c!.hfs_registry.unregistered_sections.length > 0 && (
                  <DetailLine label="Unregistered" value={c!.hfs_registry.unregistered_sections.join(', ')} />
                )}
                <DetailLine label="Index file" value={c!.hfs_registry.index_file_id} />
              </CheckRow>

            </div>
          </>
        )}
      </div>
    </div>
  )
}
