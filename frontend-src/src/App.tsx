import { useAppStore } from './store/appStore'
import ConnectPage from './pages/ConnectPage'
import OnboardPage from './pages/OnboardPage'
import SessionPage from './pages/SessionPage'

export default function App() {
  const view = useAppStore((s) => s.view)

  return (
    <div className="min-h-screen bg-surface">
      {view === 'connect' && <ConnectPage />}
      {view === 'onboard' && <OnboardPage />}
      {view === 'session' && <SessionPage />}
    </div>
  )
}
