/**
 * OnboardPage — first-time onboarding chat.
 *
 * After a new vault is provisioned and session is open, the AI guides the user
 * through customizing their harness/user/config sections.
 * The user can skip and go straight to the main session view.
 */
import { useAppStore } from '../store/appStore'
import Header from '../components/layout/Header'

export default function OnboardPage() {
  const { session, setView } = useAppStore()

  return (
    <div className="min-h-screen flex flex-col">
      <Header tokenId={session?.tokenId} />
      <main className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-lg card space-y-6 text-center">
          <div>
            <div className="text-4xl mb-3">✅</div>
            <h2 className="text-xl font-semibold text-slate-100">Companion Created</h2>
            <p className="text-slate-400 text-sm mt-2">
              Your AI companion is live on Hedera. Customize your sections in the companion editor,
              or jump straight in and let your AI guide you.
            </p>
          </div>
          <div className="flex gap-3 justify-center">
            <button onClick={() => setView('session')} className="btn-primary">
              Meet My Companion →
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}
