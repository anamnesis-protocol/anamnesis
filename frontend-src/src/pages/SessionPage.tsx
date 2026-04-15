import { useState, useEffect, useCallback } from 'react'
import { useAppStore, SuiteView } from '../store/appStore'
import { api, VaultOverall } from '../api/client'
import Header from '../components/layout/Header'
import ChatPanel from '../components/chat/ChatPanel'
import VaultSections from '../components/vault/VaultSections'
import SkillsPanel from '../components/skills/SkillsPanel'
import VaultHealthModal from '../components/vault/VaultHealthModal'
import PassPage from './PassPage'
import NotesPage from './NotesPage'
import AuthenticatorPage from './AuthenticatorPage'
import DrivePage from './DrivePage'
import MailPage from './MailPage'
import CalendarPage from './CalendarPage'
import KnowledgePage from './KnowledgePage'

type RightTab = 'vault' | 'skills'

function healthColor(overall: VaultOverall | null): string {
  if (overall === 'healthy') return 'bg-emerald-400'
  if (overall === 'degraded') return 'bg-amber-400'
  if (overall === 'critical') return 'bg-red-400'
  return 'bg-slate-600'
}

function healthLabel(overall: VaultOverall | null): string {
  if (overall === 'healthy') return 'Healthy'
  if (overall === 'degraded') return 'Degraded'
  if (overall === 'critical') return 'Critical'
  return '…'
}

interface NavItem {
  view: SuiteView
  icon: string
  label: string
}

const NAV_ITEMS: NavItem[] = [
  { view: 'chat',      icon: '💬', label: 'Chat'     },
  { view: 'pass',      icon: '🔑', label: 'Pass'     },
  { view: 'notes',     icon: '📝', label: 'Notes'    },
  { view: 'auth',      icon: '🔐', label: '2FA'      },
  { view: 'drive',     icon: '📁', label: 'Drive'    },
  { view: 'mail',      icon: '✉️',  label: 'Mail'     },
  { view: 'calendar',  icon: '📅', label: 'Calendar' },
  { view: 'knowledge', icon: '📚', label: 'Knowledge'},
]

export default function SessionPage() {
  const { session, closeSession: clearSession, pendingEdits, suiteView, setSuiteView } = useAppStore()
  const [closing, setClosing] = useState(false)
  const [rightTab, setRightTab] = useState<RightTab>('vault')
  const [vaultOverall, setVaultOverall] = useState<VaultOverall | null>(null)
  const [showHealth, setShowHealth] = useState(false)

  const fetchVaultHealth = useCallback(async () => {
    if (!session) return
    try {
      const data = await api.vault.health(session.sessionId)
      setVaultOverall(data.overall)
    } catch {
      // non-fatal
    }
  }, [session])

  useEffect(() => { fetchVaultHealth() }, [fetchVaultHealth])

  useEffect(() => {
    if (!session) return
    const sessionId = session.sessionId
    function onUnload() {
      const body = JSON.stringify({ session_id: sessionId, updated_sections: {} })
      navigator.sendBeacon('/session/close', new Blob([body], { type: 'application/json' }))
    }
    window.addEventListener('beforeunload', onUnload)
    return () => window.removeEventListener('beforeunload', onUnload)
  }, [session])

  if (!session) return null

  async function handleClose() {
    if (!session) return
    setClosing(true)
    try {
      await api.session.close(session.sessionId, pendingEdits)
    } catch {
      // best effort
    } finally {
      clearSession()
    }
  }

  const expiresDate = new Date(session.expiresAt)
  const expiresIn = Math.round((expiresDate.getTime() - Date.now()) / 60_000)

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <Header
        sessionId={session.sessionId}
        tokenId={session.tokenId}
        onClose={handleClose}
      />

      {/* Session meta bar */}
      <div className="flex items-center gap-4 px-4 py-1.5 bg-surface-card border-b border-surface-border text-xs text-slate-500">
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-emerald-400">Session active</span>
        </div>
        <span>Expires in {expiresIn}m</span>
        <span className="mono hidden sm:block truncate max-w-xs">{session.sessionId}</span>

        {/* Vault health badge */}
        <button
          onClick={() => setShowHealth(true)}
          className="flex items-center gap-1.5 ml-auto hover:text-slate-300 transition-colors"
          title="Click to view vault health details"
        >
          <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${healthColor(vaultOverall)} ${vaultOverall === null ? 'animate-pulse' : ''}`} />
          <span className={
            vaultOverall === 'healthy' ? 'text-emerald-400' :
            vaultOverall === 'degraded' ? 'text-amber-400' :
            vaultOverall === 'critical' ? 'text-red-400' :
            'text-slate-500'
          }>
            {healthLabel(vaultOverall)}
          </span>
        </button>

        {Object.keys(pendingEdits).length > 0 && (
          <span className="badge badge-yellow">
            {Object.keys(pendingEdits).length} unsaved
          </span>
        )}
      </div>

      {/* Main layout: left nav + content */}
      <div className="flex-1 flex min-h-0">

        {/* Left sidebar nav */}
        <nav className="flex flex-col gap-1 p-2 bg-surface-card border-r border-surface-border w-16 shrink-0">
          {NAV_ITEMS.map(({ view, icon, label }) => (
            <button
              key={view}
              onClick={() => setSuiteView(view)}
              title={label}
              className={`flex flex-col items-center gap-0.5 py-2 px-1 rounded-lg text-xs font-medium transition-colors ${
                suiteView === view
                  ? 'bg-brand/20 text-brand'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
              }`}
            >
              <span className="text-lg leading-none">{icon}</span>
              <span className="text-[10px]">{label}</span>
            </button>
          ))}

          {/* Spacer */}
          <div className="flex-1" />

          {/* Vault / Skills */}
          <button
            onClick={() => setSuiteView('chat')}
            title="Vault"
            className={`flex flex-col items-center gap-0.5 py-2 px-1 rounded-lg text-xs font-medium transition-colors text-slate-400 hover:text-slate-200 hover:bg-white/5`}
          >
            <span className="text-lg leading-none">🧠</span>
            <span className="text-[10px]">Vault</span>
          </button>
        </nav>

        {/* Content area */}
        {suiteView === 'chat' && (
          <>
            {/* Chat */}
            <div className="flex flex-col flex-1 min-w-0 border-r border-surface-border">
              <ChatPanel sessionId={session.sessionId} />
            </div>

            {/* Right panel: vault + skills */}
            <div className="hidden md:flex flex-col w-80 lg:w-96 shrink-0 min-h-0 overflow-hidden">
              <div className="flex border-b border-surface-border bg-surface-card">
                {(['vault', 'skills'] as RightTab[]).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setRightTab(tab)}
                    className={`flex-1 py-2 text-xs font-medium transition-colors border-b-2 ${
                      rightTab === tab
                        ? 'border-brand text-brand bg-surface-card'
                        : 'border-transparent text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {tab === 'vault' ? '🧠 Companion' : '⚡ Skills'}
                  </button>
                ))}
              </div>
              <div className="flex-1 min-h-0">
                {rightTab === 'vault' && <VaultSections sessionId={session.sessionId} />}
                {rightTab === 'skills' && <SkillsPanel sessionId={session.sessionId} />}
              </div>
            </div>
          </>
        )}

        {suiteView === 'pass'      && <PassPage         sessionId={session.sessionId} />}
        {suiteView === 'notes'     && <NotesPage        sessionId={session.sessionId} />}
        {suiteView === 'auth'      && <AuthenticatorPage sessionId={session.sessionId} />}
        {suiteView === 'drive'     && <DrivePage        sessionId={session.sessionId} />}
        {suiteView === 'mail'      && <MailPage         sessionId={session.sessionId} />}
        {suiteView === 'calendar'  && <CalendarPage     sessionId={session.sessionId} />}
        {suiteView === 'knowledge' && <KnowledgePage    sessionId={session.sessionId} />}
      </div>

      {/* Vault health modal */}
      {showHealth && (
        <VaultHealthModal
          sessionId={session.sessionId}
          onClose={() => {
            setShowHealth(false)
            fetchVaultHealth()
          }}
        />
      )}

      {/* Close overlay */}
      {closing && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="card text-center space-y-3 max-w-xs">
            <div className="text-2xl">🔒</div>
            <div className="text-slate-200 font-medium">Closing Session</div>
            <div className="text-slate-400 text-sm">
              Syncing changes to Hedera and zeroing keys…
            </div>
            <div className="flex justify-center">
              <div className="w-5 h-5 border-2 border-brand border-t-transparent rounded-full animate-spin" />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
