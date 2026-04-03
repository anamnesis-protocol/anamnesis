import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import AsyncStorage from '@react-native-async-storage/async-storage'

export interface SessionState {
  sessionId: string
  tokenId: string
  sections: Record<string, string>
  expiresAt: string
}

interface AppStore {
  // Persisted: token for returning users
  savedTokenId: string | null
  setSavedTokenId: (id: string | null) => void

  // Active session (in-memory only — never persisted)
  session: SessionState | null
  openSession: (s: SessionState) => void
  closeSession: () => void
  updateSection: (name: string, content: string) => void

  // Pending section edits tracked for diff sync on close
  pendingEdits: Record<string, string>
  setPendingEdit: (name: string, content: string) => void
  clearPendingEdits: () => void

  // UI state
  activeSection: string
  setActiveSection: (name: string) => void
  activeModel: string
  setActiveModel: (model: string) => void

  // Backend URL (configurable at runtime)
  apiBaseUrl: string
  setApiBaseUrl: (url: string) => void
}

export const useAppStore = create<AppStore>()(
  persist(
    (set, get) => ({
      savedTokenId: null,
      setSavedTokenId: (savedTokenId) => set({ savedTokenId }),

      session: null,
      openSession: (session) => set({ session, pendingEdits: {} }),
      closeSession: () => set({ session: null, pendingEdits: {} }),
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

      apiBaseUrl: 'http://localhost:8000',
      setApiBaseUrl: (apiBaseUrl) => set({ apiBaseUrl }),
    }),
    {
      name: 'context-sovereignty-app',
      storage: createJSONStorage(() => AsyncStorage),
      // Only persist token and API URL — never persist session/keys
      partialize: (state) => ({
        savedTokenId: state.savedTokenId,
        apiBaseUrl: state.apiBaseUrl,
      }),
    }
  )
)
