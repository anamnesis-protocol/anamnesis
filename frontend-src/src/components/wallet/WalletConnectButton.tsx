import { useWalletConnect } from '../../hooks/useWalletConnect'

interface Props {
  companionTokenId: string | null
  /** Called with the connected account ID — use to auto-fill account ID fields */
  onAccountId?: (accountId: string) => void
}

export default function WalletConnectButton({ companionTokenId, onAccountId }: Props) {
  const { status, accountId, ownsToken, error, connect, disconnect } = useWalletConnect(companionTokenId)

  // Notify parent when account ID becomes available
  if (accountId && onAccountId) {
    onAccountId(accountId)
  }

  if (status === 'verified' || status === 'connected') {
    return (
      <div className="flex items-center justify-between w-full bg-surface-card border border-surface-border rounded-lg px-4 py-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-slate-200">
            {ownsToken ? '✓ Ownership verified' : '⬡ Wallet connected'}
          </p>
          <p className="text-xs text-slate-500 font-mono truncate">{accountId}</p>
        </div>
        <button
          onClick={disconnect}
          className="text-slate-600 hover:text-slate-400 text-xs ml-3 transition-colors shrink-0"
        >
          Disconnect
        </button>
      </div>
    )
  }

  if (status === 'connecting') {
    return (
      <div className="flex items-center gap-2 w-full bg-surface-card border border-surface-border rounded-lg px-4 py-3">
        <div className="w-3 h-3 border-2 border-brand border-t-transparent rounded-full animate-spin shrink-0" />
        <span className="text-slate-400 text-sm">Connecting…</span>
      </div>
    )
  }

  return (
    <div className="space-y-1">
      <button
        onClick={connect}
        className="flex items-center gap-2 w-full bg-surface-card hover:bg-surface-border border border-surface-border hover:border-brand/40 rounded-lg px-4 py-3 transition-colors text-left"
      >
        <span className="text-base">⬡</span>
        <div>
          <p className="text-sm font-medium text-slate-200">Connect HashPack</p>
          <p className="text-xs text-slate-500">Auto-fill your Hedera account ID</p>
        </div>
      </button>
      {error && <p className="text-red-400 text-xs px-1">{error}</p>}
    </div>
  )
}
