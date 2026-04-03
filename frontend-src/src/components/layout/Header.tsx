interface HeaderProps {
  sessionId?: string
  tokenId?: string
  onClose?: () => void
}

export default function Header({ sessionId, tokenId, onClose }: HeaderProps) {
  return (
    <header className="border-b border-surface-border bg-surface-card px-6 py-3 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <span className="text-brand text-xl font-bold">⬡</span>
        <span className="font-semibold text-slate-100">Sovereign AI Context</span>
        <span className="badge badge-purple text-xs">PATENT PENDING</span>
      </div>

      <div className="flex items-center gap-4">
        {tokenId && (
          <span className="text-xs text-slate-500 mono hidden sm:block">
            {tokenId}
          </span>
        )}
        {sessionId && onClose && (
          <button onClick={onClose} className="btn-secondary text-xs">
            Close Session
          </button>
        )}
      </div>
    </header>
  )
}
