import React, { useState } from 'react'
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  StyleSheet,
  Alert,
} from 'react-native'
import { useAppStore } from '../store/appStore'
import { api, setBaseUrl } from '../api/client'
import { colors, s } from '../theme'

type Mode = 'returning' | 'new'
type Step = 'form' | 'sign'

export default function ConnectScreen() {
  const { savedTokenId, setSavedTokenId, openSession, apiBaseUrl, setApiBaseUrl } = useAppStore()

  const [mode, setMode] = useState<Mode>(savedTokenId ? 'returning' : 'new')
  const [step, setStep] = useState<Step>('form')
  const [tokenId, setTokenId] = useState(savedTokenId ?? '')
  const [accountId, setAccountId] = useState('')
  const [companionName, setCompanionName] = useState('')
  const [pendingTokenId, setPendingTokenId] = useState('')
  const [challengeHex, setChallengeHex] = useState('')
  const [walletSigHex, setWalletSigHex] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [showSettings, setShowSettings] = useState(false)
  const [draftUrl, setDraftUrl] = useState(apiBaseUrl)

  function setErr(msg: string) {
    setError(msg)
    setLoading(false)
  }

  async function handleReturnStart() {
    if (!tokenId.trim()) return setErr('Enter your Companion ID.')
    setLoading(true); setError('')
    try {
      setBaseUrl(apiBaseUrl)
      const data = await api.session.challenge(tokenId.trim())
      setPendingTokenId(tokenId.trim())
      setChallengeHex(data.challenge_hex)
      setStep('sign')
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  async function handleNewStart() {
    if (!accountId.trim()) return setErr('Enter your Hedera account ID.')
    if (!companionName.trim()) return setErr('Name your AI companion.')
    setLoading(true); setError('')
    try {
      setBaseUrl(apiBaseUrl)
      const data = await api.user.provisionStart(accountId.trim(), companionName.trim())
      setPendingTokenId(data.token_id)
      setChallengeHex(data.challenge_hex)
      setStep('sign')
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  async function handleDemoSign() {
    setLoading(true); setError('')
    try {
      const data = await api.chat.demoSign(pendingTokenId)
      setWalletSigHex(data.wallet_signature_hex)
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  async function handleComplete() {
    if (!walletSigHex.trim()) return setErr('Enter or generate a wallet signature.')
    setLoading(true); setError('')
    try {
      if (mode === 'new') {
        await api.user.provisionComplete(pendingTokenId, walletSigHex.trim())
      }
      const session = await api.session.open(pendingTokenId, walletSigHex.trim())
      setSavedTokenId(pendingTokenId)
      openSession({
        sessionId: session.session_id,
        tokenId: session.token_id,
        sections: session.vault_sections,
        expiresAt: session.expires_at,
      })
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  function saveSettings() {
    setApiBaseUrl(draftUrl)
    setBaseUrl(draftUrl)
    setShowSettings(false)
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>Arty Fitchels</Text>
        <TouchableOpacity onPress={() => setShowSettings(!showSettings)}>
          <Text style={styles.settingsIcon}>⚙</Text>
        </TouchableOpacity>
      </View>

      {/* Settings panel */}
      {showSettings && (
        <View style={styles.card}>
          <Text style={styles.label}>Backend URL</Text>
          <TextInput
            style={styles.input}
            value={draftUrl}
            onChangeText={setDraftUrl}
            autoCapitalize="none"
            autoCorrect={false}
            placeholder="http://192.168.1.x:8000"
            placeholderTextColor={colors.muted}
          />
          <TouchableOpacity style={styles.btnSecondary} onPress={saveSettings}>
            <Text style={styles.btnSecondaryText}>Save</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Hero */}
      <View style={styles.hero}>
        <Text style={styles.heroTitle}>Train your own AI</Text>
        <Text style={styles.heroSub}>
          Encrypted directives. Owned by you.{'\n'}Works with any AI model.
        </Text>
      </View>

      {/* Mode toggle */}
      {step === 'form' && (
        <View style={styles.toggle}>
          <TouchableOpacity
            style={[styles.toggleBtn, mode === 'returning' && styles.toggleBtnActive]}
            onPress={() => setMode('returning')}
          >
            <Text style={[styles.toggleText, mode === 'returning' && styles.toggleTextActive]}>
              I have a companion
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.toggleBtn, mode === 'new' && styles.toggleBtnActive]}
            onPress={() => setMode('new')}
          >
            <Text style={[styles.toggleText, mode === 'new' && styles.toggleTextActive]}>
              New companion
            </Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Form card */}
      <View style={styles.card}>
        {/* Returning user form */}
        {step === 'form' && mode === 'returning' && (
          <>
            <Text style={styles.label}>Companion ID</Text>
            <TextInput
              style={styles.input}
              value={tokenId}
              onChangeText={setTokenId}
              placeholder="0.0.12345"
              placeholderTextColor={colors.muted}
              autoCapitalize="none"
              autoCorrect={false}
              onSubmitEditing={handleReturnStart}
            />
            <TouchableOpacity
              style={[styles.btnPrimary, loading && styles.btnDisabled]}
              onPress={handleReturnStart}
              disabled={loading}
            >
              {loading ? (
                <ActivityIndicator color={colors.white} />
              ) : (
                <Text style={styles.btnPrimaryText}>Connect to Companion</Text>
              )}
            </TouchableOpacity>
          </>
        )}

        {/* New user form */}
        {step === 'form' && mode === 'new' && (
          <>
            <Text style={styles.label}>Hedera Account ID</Text>
            <TextInput
              style={styles.input}
              value={accountId}
              onChangeText={setAccountId}
              placeholder="0.0.99999"
              placeholderTextColor={colors.muted}
              autoCapitalize="none"
              autoCorrect={false}
            />
            <Text style={[styles.label, { marginTop: 12 }]}>Name your AI</Text>
            <TextInput
              style={styles.input}
              value={companionName}
              onChangeText={setCompanionName}
              placeholder="Aria, Atlas, Nova…"
              placeholderTextColor={colors.muted}
              onSubmitEditing={handleNewStart}
            />
            <TouchableOpacity
              style={[styles.btnPrimary, loading && styles.btnDisabled]}
              onPress={handleNewStart}
              disabled={loading}
            >
              {loading ? (
                <ActivityIndicator color={colors.white} />
              ) : (
                <Text style={styles.btnPrimaryText}>Mint My Companion</Text>
              )}
            </TouchableOpacity>
          </>
        )}

        {/* Sign step */}
        {step === 'sign' && (
          <>
            <Text style={styles.label}>Token ID</Text>
            <Text style={styles.mono}>{pendingTokenId}</Text>

            <Text style={[styles.label, { marginTop: 12 }]}>Challenge</Text>
            <Text style={[styles.mono, styles.small]} numberOfLines={2}>{challengeHex}</Text>

            <Text style={[styles.label, { marginTop: 12 }]}>Wallet Signature (hex)</Text>
            <TextInput
              style={[styles.input, styles.mono, styles.small]}
              value={walletSigHex}
              onChangeText={setWalletSigHex}
              placeholder="Paste Ed25519 signature…"
              placeholderTextColor={colors.muted}
              autoCapitalize="none"
              autoCorrect={false}
              multiline
            />

            <View style={styles.row}>
              <TouchableOpacity
                style={[styles.btnSecondary, styles.flex1, loading && styles.btnDisabled]}
                onPress={handleDemoSign}
                disabled={loading}
              >
                {loading ? (
                  <ActivityIndicator color={colors.brand} />
                ) : (
                  <Text style={styles.btnSecondaryText}>⚡ Demo Sign</Text>
                )}
              </TouchableOpacity>
              <View style={{ width: 8 }} />
              <TouchableOpacity
                style={[
                  styles.btnPrimary,
                  styles.flex1,
                  (!walletSigHex || loading) && styles.btnDisabled,
                ]}
                onPress={handleComplete}
                disabled={!walletSigHex || loading}
              >
                {loading ? (
                  <ActivityIndicator color={colors.white} />
                ) : (
                  <Text style={styles.btnPrimaryText}>
                    {mode === 'new' ? 'Connect' : 'Open Companion'}
                  </Text>
                )}
              </TouchableOpacity>
            </View>

            <TouchableOpacity
              style={styles.btnGhost}
              onPress={() => { setStep('form'); setError(''); setWalletSigHex('') }}
            >
              <Text style={styles.btnGhostText}>← Back</Text>
            </TouchableOpacity>
          </>
        )}

        {error !== '' && (
          <View style={styles.errorBox}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}
      </View>

      <Text style={styles.footer}>
        Secured by Hedera Hashgraph · End-to-end encrypted · Patent pending
      </Text>
    </ScrollView>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  content: { padding: 20, paddingTop: 60, paddingBottom: 40 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 },
  title: { fontSize: 18, fontWeight: '700', color: colors.text },
  settingsIcon: { fontSize: 20, color: colors.muted },
  hero: { alignItems: 'center', marginBottom: 28 },
  heroTitle: { fontSize: 28, fontWeight: '800', color: colors.text, marginBottom: 8 },
  heroSub: { fontSize: 14, color: colors.muted, textAlign: 'center', lineHeight: 20 },
  toggle: { flexDirection: 'row', borderRadius: 10, borderWidth: 1, borderColor: colors.border, overflow: 'hidden', marginBottom: 16 },
  toggleBtn: { flex: 1, paddingVertical: 10, alignItems: 'center', backgroundColor: colors.card },
  toggleBtnActive: { backgroundColor: colors.brand },
  toggleText: { fontSize: 14, fontWeight: '500', color: colors.muted },
  toggleTextActive: { color: colors.white },
  card: { backgroundColor: colors.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: colors.border, marginBottom: 16 },
  label: { fontSize: 12, color: colors.muted, marginBottom: 4 },
  input: { backgroundColor: colors.inputBg, borderRadius: 8, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 12, paddingVertical: 10, color: colors.text, fontSize: 14, marginBottom: 12 },
  mono: { fontFamily: 'monospace', color: colors.brand, fontSize: 13 },
  small: { fontSize: 11, color: colors.muted },
  btnPrimary: { backgroundColor: colors.brand, borderRadius: 8, paddingVertical: 12, alignItems: 'center', marginTop: 4 },
  btnPrimaryText: { color: colors.white, fontWeight: '600', fontSize: 15 },
  btnSecondary: { borderWidth: 1, borderColor: colors.brand, borderRadius: 8, paddingVertical: 12, alignItems: 'center' },
  btnSecondaryText: { color: colors.brand, fontWeight: '600', fontSize: 14 },
  btnGhost: { paddingVertical: 10, alignItems: 'center', marginTop: 4 },
  btnGhostText: { color: colors.muted, fontSize: 13 },
  btnDisabled: { opacity: 0.5 },
  row: { flexDirection: 'row', marginTop: 8 },
  flex1: { flex: 1 },
  errorBox: { backgroundColor: 'rgba(239,68,68,0.1)', borderWidth: 1, borderColor: 'rgba(239,68,68,0.4)', borderRadius: 8, padding: 10, marginTop: 8 },
  errorText: { color: '#f87171', fontSize: 12 },
  footer: { textAlign: 'center', fontSize: 11, color: colors.subtle, marginTop: 8 },
})
