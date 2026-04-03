import { useState } from 'react'
import { useAppStore } from '../store/appStore'
import { api } from '../api/client'
import Header from '../components/layout/Header'
import ChatPanel from '../components/chat/ChatPanel'
import VaultSections from '../components/vault/VaultSections'
import SkillsPanel from '../components/skills/SkillsPanel'

type RightTab = 'vault' | 'skills'

export default function SessionPage() {
  const { session, closeSession: clearSession, pendingEdits } = useAppStore()
  const [closing, setClosing] = useState(false)
  const [rightTab, setRightTab] = useState<RightTab>('vault')

  if (!session) return null

  async function handleClose() {
    if (!session) return
    setClosing(true)
    try {
      await api.session.close(session.sessionId, pendingEdits)
    } catch {
      // best effort — still clear local state
    } finally {
      clearSession()
    }
  }

  const expiresDate = new Date(session.expiresAt)
  const expiresIn = Math.round((expiresDate.getTime() - Date.now()) / 60_000)

  return (
    <div className="min-h-screen flex flex-col">
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
        {Object.keys(pendingEdits).length > 0 && (
          <span className="badge badge-yellow ml-auto">
            {Object.keys(pendingEdits).length} unsaved edit{Object.keys(pendingEdits).length > 1 ? 's' : ''} — saved on close
          </span>
        )}
      </div>

      {/* Main layout: chat left, vault/skills right */}
      <div className="flex-1 flex min-h-0">
        {/* Left: Chat */}
        <div className="flex flex-col flex-1 min-w-0 border-r border-surface-border">
          <ChatPanel sessionId={session.sessionId} />
        </div>

        {/* Right: Vault + Skills — collapsible on small screens */}
        <div className="hidden md:flex flex-col w-80 lg:w-96 shrink-0">
          {/* Tab bar */}
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
                {tab === 'vault' ? '🔐 Vault' : '🧠 Skills'}
              </button>
            ))}
          </div>

          <div className="flex-1 min-h-0">
            {rightTab === 'vault' && (
              <VaultSections sessionId={session.sessionId} />
            )}
            {rightTab === 'skills' && (
              <SkillsPanel sessionId={session.sessionId} />
            )}
          </div>
        </div>
      </div>

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
