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
  const hcRef = useRef<any>(null)

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved && companionTokenId) {
        setState(s => ({ ...s, status: 'connecting', accountId: saved }))
        checkTokenOwnership(saved, companionTokenId).then(owns => {
          setState(s => ({
            ...s,
            status: owns ? 'verified' : 'connected',
            ownsToken: owns,
          }))
        })
      }
    } catch { /* ignore */ }

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let hc: any

    async function setup() {
      const { HashConnect } = await import('hashconnect')

      const ledger = {
        toString: () => NETWORK,
        isMainnet: () => NETWORK === 'mainnet',
        isTestnet: () => NETWORK === 'testnet',
        isPreviewnet: () => false,
        _ledgerId: NETWORK,
      } as any // eslint-disable-line @typescript-eslint/no-explicit-any

      hc = new HashConnect(
        ledger,
        PROJECT_ID,
        {
          name: 'Arty Fitchels',
          description: 'Your persistent AI companion',
          url: 'https://artyfitchels.ai',
          icons: ['https://artyfitchels.ai/icon.png'],
        },
        false
      )

      hcRef.current = hc

      hc.pairingEvent.on(async (data: any) => { // eslint-disable-line @typescript-eslint/no-explicit-any
        const accountId = data.accountIds?.[0]?.toString() ?? null
        if (!accountId) return

        try { localStorage.setItem(STORAGE_KEY, accountId) } catch { /* ignore */ }

        setState(s => ({ ...s, status: 'connecting', accountId, error: null }))

        if (tokenIdRef.current) {
          const owns = await checkTokenOwnership(accountId, tokenIdRef.current)
          setState(s => ({
            ...s,
            status: owns ? 'verified' : 'connected',
            ownsToken: owns,
          }))
        } else {
          setState(s => ({ ...s, status: 'connected', ownsToken: false }))
        }
      })

      hc.disconnectionEvent.on(() => {
        try { localStorage.removeItem(STORAGE_KEY) } catch { /* ignore */ }
        setState({ status: 'idle', accountId: null, ownsToken: false, error: null })
      })

      await hc.init()

      const existing = hc.connectedAccountIds?.[0]?.toString() ?? null
      if (existing && tokenIdRef.current) {
        setState(s => ({ ...s, status: 'connecting', accountId: existing }))
        const owns = await checkTokenOwnership(existing, tokenIdRef.current)
        setState(s => ({
          ...s,
          status: owns ? 'verified' : 'connected',
          ownsToken: owns,
        }))
      }
    }

    setup().catch(err => {
      setState(s => ({ ...s, status: 'error', error: String(err) }))
    })

    return () => {
      hcRef.current?.disconnect().catch(() => {})
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const connect = useCallback(async () => {
    if (!hcRef.current) return
    setState(s => ({ ...s, status: 'connecting', error: null }))
    try {
      await hcRef.current.openPairingModal('dark', '#0f172a', '#7c3aed', '#7c3aed', '8px')
    } catch (e) {
      setState(s => ({ ...s, status: 'error', error: String(e) }))
    }
  }, [])

  const disconnect = useCallback(async () => {
    if (!hcRef.current) return
    await hcRef.current.disconnect()
  }, [])

  return { ...state, connect, disconnect }
}
