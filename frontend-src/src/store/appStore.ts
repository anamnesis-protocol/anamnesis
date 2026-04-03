import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type AppView = 'connect' | 'onboard' | 'session'

export interface SessionState {
  sessionId: string
  tokenId: string
  sections: Record<string, string>
  expiresAt: string
}

interface AppStore {
  // Routing
  view: AppView
  setView: (v: AppView) => void

  // Persisted: token for returning users
  savedTokenId: string | null
  setSavedTokenId: (id: string | null) => void

  // Active session (in-memory only)
  session: SessionState | null
  openSession: (s: SessionState) => void
  closeSession: () => void
  updateSection: (name: string, content: string) => void

  // Pending section edits — tracked for diff sync on close
  pendingEdits: Record<string, string>
  setPendingEdit: (name: string, content: string) => void
  clearPendingEdits: () => void

  // UI state
  activeSection: string
  setActiveSection: (name: string) => void
  activeModel: string
  setActiveModel: (model: string) => void
}

export const useAppStore = create<AppStore>()(
  persist(
    (set, get) => ({
      view: 'connect',
      setView: (view) => set({ view }),

      savedTokenId: null,
      setSavedTokenId: (savedTokenId) => set({ savedTokenId }),

      session: null,
      openSession: (session) => set({ session, view: 'session', pendingEdits: {} }),
      closeSession: () => set({ session: null, view: 'connect', pendingEdits: {} }),
      updateSection: (name, content) =>
        set((state) => ({
          session: state.session
            ? { ...state.session, sections: { ...state.session.sections, [name]: content } }
            : null,
        })),

      pendingEdits: {},
      setPendingEdit: (name, content) =>
        set((state) => ({ pendingEdits: { ...state.pendingEdits, [name]: content } })),
      clearPendingEdits: () => set({ pendingEdits: {} }),

      activeSection: 'harness',
      setActiveSection: (activeSection) => set({ activeSection }),
      activeModel: '',
      setActiveModel: (activeModel) => set({ activeModel }),
    }),
    {
      name: 'arty-fitchels-app',
      // Only persist the token — never persist session/keys
      partialize: (state) => ({ savedTokenId: state.savedTokenId }),
    }
  )
)
