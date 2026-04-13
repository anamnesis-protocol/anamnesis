import { useState } from 'react'
import { useAppStore } from '../store/appStore'
import { api } from '../api/client'
import Header from '../components/layout/Header'

type Mode = 'returning' | 'new'

export default function ConnectPage() {
  const { savedTokenId, setSavedTokenId, setView, openSession } = useAppStore()

  const [mode, setMode] = useState<Mode>(savedTokenId ? 'returning' : 'new')
  const [tokenId, setTokenId] = useState(savedTokenId ?? '')
  const [accountId, setAccountId] = useState('')
  const [companionName, setCompanionName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Provisioning state (new user flow)
  const [step, setStep] = useState<'form' | 'sign' | 'complete'>('form')
  const [pendingTokenId, setPendingTokenId] = useState('')
  const [challengeHex, setChallengeHex] = useState('')
  const [walletSigHex, setWalletSigHex] = useState('')

  function err(msg: string) {
    setError(msg)
    setLoading(false)
  }

  // ── Returning user: get challenge → show sign step
  async function handleReturnStart() {
    if (!tokenId.trim()) return err('Enter your token ID.')
    setLoading(true)
    setError('')
    try {
      const data = await api.session.challenge(tokenId.trim())
      setPendingTokenId(tokenId.trim())
      setChallengeHex(data.challenge_hex)
      setStep('sign')
    } catch (e: unknown) {
      err(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  // ── New user: provision start → show sign step
  async function handleNewStart() {
    if (!accountId.trim()) return err('Enter an account ID or name.')
    if (!companionName.trim()) return err('Name your AI companion.')
    setLoading(true)
    setError('')
    try {
      const data = await api.user.provisionStart(accountId.trim(), companionName.trim())
      setPendingTokenId(data.token_id)
      setChallengeHex(data.challenge_hex)
      setStep('sign')
    } catch (e: unknown) {
      err(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  // ── Demo sign (operator key, server-side) — calls /demo/sign
  async function handleDemoSign() {
    if (!walletSigHex) {
      // For demo mode: auto-generate a signature client-side by calling /demo/sign
      setLoading(true)
      setError('')
      try {
        const res = await fetch('/demo/sign', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token_id: pendingTokenId }),
        })
        const data = await res.json()
        if (!res.ok) throw new Error(data.detail ?? 'Demo sign failed')
        setWalletSigHex(data.signature_hex)
      } catch (e: unknown) {
        err(e instanceof Error ? e.message : String(e))
      } finally {
        setLoading(false)
      }
    }
  }

  // ── Complete: provision complete (new) OR open session (returning)
  async function handleComplete() {
    if (!walletSigHex.trim()) return err('Enter or generate a wallet signature.')
    setLoading(true)
    setError('')
    try {
      // For new users: complete provisioning first
      if (mode === 'new' && step === 'sign') {
        await api.user.provisionComplete(pendingTokenId, walletSigHex.trim())
      }

      // Open session
      const session = await api.session.open(pendingTokenId, walletSigHex.trim())
      setSavedTokenId(pendingTokenId)
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
          {step === 'form' && (
            <div className="flex rounded-lg border border-surface-border overflow-hidden">
              <button
                onClick={() => setMode('returning')}
                className={`flex-1 py-2 text-sm font-medium transition-colors ${
                  mode === 'returning'
                    ? 'bg-brand text-white'
                    : 'bg-surface-card text-slate-400 hover:text-slate-200'
                }`}
              >
                I have a companion
              </button>
              <button
                onClick={() => setMode('new')}
                className={`flex-1 py-2 text-sm font-medium transition-colors ${
                  mode === 'new'
                    ? 'bg-brand text-white'
                    : 'bg-surface-card text-slate-400 hover:text-slate-200'
                }`}
              >
                New to Arty Fitchels
              </button>
            </div>
          )}

          {/* Form */}
          <div className="card space-y-4">
            {/* ── Step: form ── */}
            {step === 'form' && mode === 'returning' && (
              <>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Companion ID</label>
                  <input
                    className="input"
                    placeholder="0.0.12345"
                    value={tokenId}
                    onChange={(e) => setTokenId(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleReturnStart()}
                  />
                </div>
                <button onClick={handleReturnStart} disabled={loading} className="btn-primary w-full">
                  {loading ? 'Connecting…' : 'Connect to Companion'}
                </button>
              </>
            )}

            {step === 'form' && mode === 'new' && (
              <>
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
                    onKeyDown={(e) => e.key === 'Enter' && handleNewStart()}
                  />
                </div>
                <button onClick={handleNewStart} disabled={loading} className="btn-primary w-full">
                  {loading ? 'Creating companion…' : 'Meet Your AI'}
                </button>
              </>
            )}

            {/* ── Step: sign ── */}
            {step === 'sign' && (
              <div className="space-y-4">
                <div>
                  <div className="text-xs text-slate-400 mb-1">Companion ID</div>
                  <div className="mono text-sm text-brand">{pendingTokenId}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-400 mb-1">Challenge</div>
                  <div className="mono text-xs text-slate-500 break-all line-clamp-2">
                    {challengeHex}
                  </div>
                </div>

                <div>
                  <label className="block text-xs text-slate-400 mb-1">
                    Wallet Signature (hex)
                  </label>
                  <input
                    className="input mono text-xs"
                    placeholder="Paste Ed25519/secp256k1 signature…"
                    value={walletSigHex}
                    onChange={(e) => setWalletSigHex(e.target.value)}
                  />
                </div>

                <div className="flex gap-2">
                  <button
                    onClick={handleDemoSign}
                    disabled={loading}
                    className="btn-secondary flex-1"
                  >
                    {loading ? '…' : '⚡ Demo Sign'}
                  </button>
                  <button
                    onClick={handleComplete}
                    disabled={loading || !walletSigHex}
                    className="btn-primary flex-1"
                  >
                    {loading
                      ? 'Opening…'
                      : mode === 'new'
                      ? 'Connect'
                      : 'Open Companion'}
                  </button>
                </div>

                <button
                  onClick={() => { setStep('form'); setError(''); setWalletSigHex('') }}
                  className="btn-ghost w-full text-xs"
                >
                  ← Back
                </button>
              </div>
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
