import { useState } from 'react'
import { useAppStore } from '../store/appStore'
import { api } from '../api/client'
import Header from '../components/layout/Header'
import WalletConnectButton from '../components/wallet/WalletConnectButton'

type Mode = 'returning' | 'new'

export default function ConnectPage() {
  const { savedTokenId, setSavedTokenId, openSession } = useAppStore()

  const [mode, setMode] = useState<Mode>(savedTokenId ? 'returning' : 'new')
  const [tokenId, setTokenId] = useState(savedTokenId ?? '')
  const [passphrase, setPassphrase] = useState('')
  const [showPassphrase, setShowPassphrase] = useState(false)

  // New user fields
  const [accountId, setAccountId] = useState('')
  const [companionName, setCompanionName] = useState('')
  const [newPassphrase, setNewPassphrase] = useState('')
  const [confirmPassphrase, setConfirmPassphrase] = useState('')

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  function err(msg: string) {
    setError(msg)
    setLoading(false)
  }

  // ── Returning user: open session with passphrase
  async function handleConnect() {
    if (!tokenId.trim()) return err('Enter your companion ID.')
    if (passphrase.length < 8) return err('Passphrase must be at least 8 characters.')
    setLoading(true)
    setError('')
    try {
      const session = await api.session.open(tokenId.trim(), { passphrase })
      setSavedTokenId(session.token_id)
      openSession({
        sessionId: session.session_id,
        tokenId: session.token_id,
        sections: session.context_sections ?? {},
        expiresAt: session.expires_at,
      })
    } catch (e: unknown) {
      err(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  // ── New user: provision then open session
  async function handleCreate() {
    if (!accountId.trim()) return err('Enter your Hedera account ID.')
    if (!companionName.trim()) return err('Name your AI companion.')
    if (newPassphrase.length < 8) return err('Passphrase must be at least 8 characters.')
    if (newPassphrase !== confirmPassphrase) return err('Passphrases do not match.')
    setLoading(true)
    setError('')
    try {
      // Provision: start → complete using passphrase as wallet sig placeholder for demo
      const start = await api.user.provisionStart(accountId.trim(), companionName.trim())
      await api.user.provisionComplete(start.token_id, newPassphrase)
      // Open session
      const session = await api.session.open(start.token_id, { passphrase: newPassphrase })
      setSavedTokenId(session.token_id)
      openSession({
        sessionId: session.session_id,
        tokenId: session.token_id,
        sections: session.context_sections ?? {},
        expiresAt: session.expires_at,
      })
    } catch (e: unknown) {
      err(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Header />

      <main className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-md space-y-6">

          {/* Hero */}
          <div className="text-center space-y-2">
            <h1 className="text-3xl font-bold text-slate-100">Train your own AI</h1>
            <p className="text-slate-400 text-sm">
              Encrypted directives. Owned by you. Works with any AI model.
            </p>
          </div>

          {/* Mode toggle */}
          <div className="flex rounded-lg border border-surface-border overflow-hidden">
            <button
              onClick={() => { setMode('returning'); setError('') }}
              className={`flex-1 py-2 text-sm font-medium transition-colors ${
                mode === 'returning'
                  ? 'bg-brand text-white'
                  : 'bg-surface-card text-slate-400 hover:text-slate-200'
              }`}
            >
              I have a companion
            </button>
            <button
              onClick={() => { setMode('new'); setError('') }}
              className={`flex-1 py-2 text-sm font-medium transition-colors ${
                mode === 'new'
                  ? 'bg-brand text-white'
                  : 'bg-surface-card text-slate-400 hover:text-slate-200'
              }`}
            >
              New to Arty Fitchels
            </button>
          </div>

          {/* Form */}
          <div className="card space-y-4">

            {/* ── Returning user ── */}
            {mode === 'returning' && (
              <>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Companion ID</label>
                  <input
                    className="input"
                    placeholder="0.0.12345"
                    value={tokenId}
                    onChange={(e) => setTokenId(e.target.value)}
                    autoComplete="username"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Passphrase</label>
                  <div className="relative">
                    <input
                      className="input pr-10"
                      type={showPassphrase ? 'text' : 'password'}
                      placeholder="Your vault passphrase"
                      value={passphrase}
                      onChange={(e) => setPassphrase(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleConnect()}
                      autoComplete="current-password"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassphrase((v) => !v)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 text-xs"
                    >
                      {showPassphrase ? 'hide' : 'show'}
                    </button>
                  </div>
                </div>
                <button onClick={handleConnect} disabled={loading} className="btn-primary w-full">
                  {loading ? 'Opening…' : 'Open Companion'}
                </button>
              </>
            )}

            {/* ── New user ── */}
            {mode === 'new' && (
              <>
                <WalletConnectButton
                  companionTokenId={null}
                  onAccountId={(id) => setAccountId(id)}
                />
                <div className="relative flex items-center">
                  <div className="flex-1 border-t border-surface-border" />
                  <span className="px-3 text-xs text-slate-600">or enter manually</span>
                  <div className="flex-1 border-t border-surface-border" />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Your Hedera Account ID</label>
                  <input
                    className="input"
                    placeholder="0.0.99999"
                    value={accountId}
                    onChange={(e) => setAccountId(e.target.value)}
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Name your AI</label>
                  <input
                    className="input"
                    placeholder="e.g. Aria, Atlas, Nova…"
                    value={companionName}
                    onChange={(e) => setCompanionName(e.target.value)}
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Create a passphrase</label>
                  <input
                    className="input"
                    type="password"
                    placeholder="At least 8 characters"
                    value={newPassphrase}
                    onChange={(e) => setNewPassphrase(e.target.value)}
                    autoComplete="new-password"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Confirm passphrase</label>
                  <input
                    className="input"
                    type="password"
                    placeholder="Repeat passphrase"
                    value={confirmPassphrase}
                    onChange={(e) => setConfirmPassphrase(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
                    autoComplete="new-password"
                  />
                </div>
                <button onClick={handleCreate} disabled={loading} className="btn-primary w-full">
                  {loading ? 'Creating companion…' : 'Meet Your AI'}
                </button>
              </>
            )}

            {error && (
              <div className="text-red-400 text-xs bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">
                {error}
              </div>
            )}
          </div>

          {/* Bottom hint */}
          <p className="text-center text-xs text-slate-600">
            Secured by Hedera Hashgraph · End-to-end encrypted · Patent pending
          </p>
        </div>
      </main>
    </div>
  )
}
