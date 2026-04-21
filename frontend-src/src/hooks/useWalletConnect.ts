import { useState, useEffect, useRef, useCallback } from 'react'

export type WalletStatus = 'idle' | 'connecting' | 'connected' | 'verified' | 'error'

export interface WalletState {
  status: WalletStatus
  accountId: string | null
  ownsToken: boolean
  error: string | null
}

const NETWORK = import.meta.env.VITE_HEDERA_NETWORK ?? 'testnet'
const PROJECT_ID = import.meta.env.VITE_WALLETCONNECT_PROJECT_ID ?? ''
const MIRROR_BASE =
  NETWORK === 'mainnet'
    ? 'https://mainnet-public.mirrornode.hedera.com'
    : 'https://testnet.mirrornode.hedera.com'

const STORAGE_KEY = 'af-wallet-account'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function makeLedgerId(network: string): any {
  return {
    toString: () => network,
    isMainnet: () => network === 'mainnet',
    isTestnet: () => network === 'testnet',
    isPreviewnet: () => false,
    _ledgerId: network,
  }
}

async function checkTokenOwnership(accountId: string, tokenId: string): Promise<boolean> {
  try {
    const res = await fetch(
      `${MIRROR_BASE}/api/v1/accounts/${accountId}/tokens?token.id=${tokenId}&limit=1`
    )
    if (!res.ok) return false
    const data = await res.json()
    return Array.isArray(data.tokens) && data.tokens.length > 0
  } catch {
    return false
  }
}

export function useWalletConnect(companionTokenId: string | null) {
  const [state, setState] = useState<WalletState>({
    status: 'idle',
    accountId: null,
    ownsToken: false,
    error: null,
  })

  const tokenIdRef = useRef(companionTokenId)
  tokenIdRef.current = companionTokenId

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const connectorRef = useRef<any>(null)

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved && companionTokenId) {
        setState(s => ({ ...s, status: 'connecting', accountId: saved }))
        checkTokenOwnership(saved, companionTokenId).then(owns => {
          setState(s => ({ ...s, status: owns ? 'verified' : 'connected', ownsToken: owns }))
        })
      }
    } catch { /* ignore */ }

    async function setup() {
      const { DAppConnector } = await import('@hashgraph/hedera-wallet-connect')

      const connector = new DAppConnector(
        {
          name: 'Arty Fitchels',
          description: 'Your persistent AI companion',
          url: 'https://artyfitchels.ai',
          icons: ['https://artyfitchels.ai/icon.png'],
        },
        makeLedgerId(NETWORK),
        PROJECT_ID
      )

      connectorRef.current = connector
      await connector.init()

      const existing = connector.signers?.[0]?.getAccountId?.()?.toString() ?? null
      if (existing) {
        try { localStorage.setItem(STORAGE_KEY, existing) } catch { /* ignore */ }
        if (tokenIdRef.current) {
          const owns = await checkTokenOwnership(existing, tokenIdRef.current)
          setState(s => ({ ...s, status: owns ? 'verified' : 'connected', accountId: existing, ownsToken: owns }))
        } else {
          setState(s => ({ ...s, status: 'connected', accountId: existing }))
        }
      }

      connector.walletConnectClient?.on('session_delete', () => {
        try { localStorage.removeItem(STORAGE_KEY) } catch { /* ignore */ }
        setState({ status: 'idle', accountId: null, ownsToken: false, error: null })
      })
    }

    setup().catch(err => {
      setState(s => ({ ...s, status: 'error', error: String(err) }))
    })

    return () => {
      connectorRef.current?.disconnectAll().catch(() => {})
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const connect = useCallback(async () => {
    if (!connectorRef.current) return
    setState(s => ({ ...s, status: 'connecting', error: null }))
    try {
      await connectorRef.current.openModal()

      const accountId = connectorRef.current.signers?.[0]?.getAccountId?.()?.toString() ?? null
      if (!accountId) {
        setState(s => ({ ...s, status: 'idle' }))
        return
      }

      try { localStorage.setItem(STORAGE_KEY, accountId) } catch { /* ignore */ }

      if (tokenIdRef.current) {
        const owns = await checkTokenOwnership(accountId, tokenIdRef.current)
        setState(s => ({ ...s, status: owns ? 'verified' : 'connected', accountId, ownsToken: owns, error: null }))
      } else {
        setState(s => ({ ...s, status: 'connected', accountId, ownsToken: false, error: null }))
      }
    } catch {
      setState(s => ({ ...s, status: 'idle', error: null }))
    }
  }, [])

  const disconnect = useCallback(async () => {
    if (!connectorRef.current) return
    try { await connectorRef.current.disconnectAll() } catch { /* ignore */ }
    try { localStorage.removeItem(STORAGE_KEY) } catch { /* ignore */ }
    setState({ status: 'idle', accountId: null, ownsToken: false, error: null })
  }, [])

  return { ...state, connect, disconnect }
}
