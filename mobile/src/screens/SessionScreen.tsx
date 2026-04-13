import React, { useEffect, useState } from 'react'
import {
  View,
  Text,
  TouchableOpacity,
  Alert,
  StyleSheet,
  SafeAreaView,
  StatusBar,
} from 'react-native'
import { useAppStore } from '../store/appStore'
import { api } from '../api/client'
import ChatPanel from '../components/chat/ChatPanel'
import VaultSections from '../components/vault/VaultSections'
import { colors } from '../theme'
import { ModelInfo } from '../api/client'

type Tab = 'chat' | 'vault'

export default function SessionScreen() {
  const {
    session,
    closeSession,
    pendingEdits,
    clearPendingEdits,
    activeModel,
    setActiveModel,
  } = useAppStore()

  const [tab, setTab] = useState<Tab>('chat')
  const [models, setModels] = useState<ModelInfo[]>([])
  const [closing, setClosing] = useState(false)

  useEffect(() => {
    if (!session) return
    api.chat.models(session.sessionId)
      .then((res) => {
        const avail = res.models.filter((m) => m.available)
        setModels(avail)
        if (!activeModel && avail.length > 0) {
          setActiveModel(avail[0].id)
        }
      })
      .catch(() => {})
  }, [session?.sessionId])

  async function handleClose() {
    if (!session) return
    const hasPending = Object.keys(pendingEdits).length > 0

    if (hasPending) {
      Alert.alert(
        'Save changes?',
        'You have unsaved companion edits. Save them before closing?',
        [
          {
            text: 'Discard',
            style: 'destructive',
            onPress: () => doClose({}),
          },
          {
            text: 'Save & Close',
            onPress: () => doClose(pendingEdits),
          },
          { text: 'Cancel', style: 'cancel' },
        ]
      )
    } else {
      doClose({})
    }
  }

  async function doClose(updatedSections: Record<string, string>) {
    if (!session || closing) return
    setClosing(true)
    try {
      await api.session.close(session.sessionId, updatedSections)
    } catch {
      // best-effort close
    } finally {
      clearPendingEdits()
      closeSession()
      setClosing(false)
    }
  }

  if (!session) return null

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor={colors.bg} />

      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.headerTitle}>Companion Active</Text>
          <Text style={styles.headerSub} numberOfLines={1}>
            {session.tokenId}
          </Text>
        </View>
        <TouchableOpacity
          style={[styles.closeBtn, closing && styles.closeBtnDisabled]}
          onPress={handleClose}
          disabled={closing}
        >
          <Text style={styles.closeBtnText}>{closing ? 'Closing…' : 'End Session'}</Text>
        </TouchableOpacity>
      </View>

      {/* Tab bar */}
      <View style={styles.tabBar}>
        <TouchableOpacity
          style={[styles.tabBtn, tab === 'chat' && styles.tabBtnActive]}
          onPress={() => setTab('chat')}
        >
          <Text style={[styles.tabBtnText, tab === 'chat' && styles.tabBtnTextActive]}>
            Chat
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tabBtn, tab === 'vault' && styles.tabBtnActive]}
          onPress={() => setTab('vault')}
        >
          <Text style={[styles.tabBtnText, tab === 'vault' && styles.tabBtnTextActive]}>
            Vault{Object.keys(pendingEdits).length > 0 ? ' •' : ''}
          </Text>
        </TouchableOpacity>
      </View>

      {/* Content */}
      <View style={styles.content}>
        {tab === 'chat' ? (
          <ChatPanel
            sessionId={session.sessionId}
            model={activeModel}
            availableModels={models.map((m) => ({ id: m.id, display: m.display }))}
            onModelChange={setActiveModel}
          />
        ) : (
          <VaultSections />
        )}
      </View>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  headerTitle: { fontSize: 16, fontWeight: '700', color: colors.text },
  headerSub: { fontSize: 11, color: colors.muted, marginTop: 2, maxWidth: 200 },
  closeBtn: { paddingHorizontal: 14, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: colors.border },
  closeBtnDisabled: { opacity: 0.5 },
  closeBtnText: { fontSize: 13, color: colors.muted },
  tabBar: { flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: colors.border },
  tabBtn: { flex: 1, paddingVertical: 12, alignItems: 'center' },
  tabBtnActive: { borderBottomWidth: 2, borderBottomColor: colors.brand },
  tabBtnText: { fontSize: 14, fontWeight: '500', color: colors.muted },
  tabBtnTextActive: { color: colors.brandLight },
  content: { flex: 1 },
})
