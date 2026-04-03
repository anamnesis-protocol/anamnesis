import React, { useState, useRef, useEffect } from 'react'
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  FlatList,
  ActivityIndicator,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
} from 'react-native'
import { useChat, Message } from '../../hooks/useChat'
import { colors } from '../../theme'

interface Props {
  sessionId: string
  model: string
  availableModels: Array<{ id: string; display: string }>
  onModelChange: (id: string) => void
}

export default function ChatPanel({ sessionId, model, availableModels, onModelChange }: Props) {
  const { messages, streaming, error, send, abort } = useChat(sessionId, model)
  const [input, setInput] = useState('')
  const listRef = useRef<FlatList<Message>>(null)

  useEffect(() => {
    if (messages.length > 0) {
      listRef.current?.scrollToEnd({ animated: true })
    }
  }, [messages])

  function handleSend() {
    const text = input.trim()
    if (!text) return
    setInput('')
    send(text)
  }

  function renderMessage({ item }: { item: Message }) {
    const isUser = item.role === 'user'
    return (
      <View style={[styles.bubble, isUser ? styles.userBubble : styles.aiBubble]}>
        {!isUser && (
          <Text style={styles.modelLabel}>
            {item.model ?? 'AI'}
          </Text>
        )}
        <Text style={[styles.bubbleText, isUser && styles.userText]}>
          {item.content || (streaming ? '▋' : '')}
        </Text>
      </View>
    )
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
    >
      {/* Model picker */}
      {availableModels.length > 1 && (
        <View style={styles.modelRow}>
          {availableModels.map((m) => (
            <TouchableOpacity
              key={m.id}
              style={[styles.modelChip, model === m.id && styles.modelChipActive]}
              onPress={() => onModelChange(m.id)}
            >
              <Text style={[styles.modelChipText, model === m.id && styles.modelChipTextActive]}>
                {m.display}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      )}

      {/* Messages */}
      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(m) => m.id}
        renderItem={renderMessage}
        contentContainerStyle={styles.messages}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyText}>Start a conversation</Text>
          </View>
        }
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: false })}
      />

      {/* Error */}
      {error !== '' && (
        <View style={styles.errorBar}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      )}

      {/* Input */}
      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder="Message…"
          placeholderTextColor={colors.muted}
          multiline
          maxLength={4000}
          editable={!streaming}
        />
        <TouchableOpacity
          style={[styles.sendBtn, streaming && styles.sendBtnStreaming]}
          onPress={streaming ? abort : handleSend}
          disabled={!streaming && !input.trim()}
        >
          {streaming ? (
            <Text style={styles.sendBtnText}>■</Text>
          ) : (
            <Text style={styles.sendBtnText}>↑</Text>
          )}
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  modelRow: { flexDirection: 'row', flexWrap: 'wrap', padding: 8, gap: 6, borderBottomWidth: 1, borderBottomColor: colors.border },
  modelChip: { borderRadius: 20, paddingHorizontal: 10, paddingVertical: 4, borderWidth: 1, borderColor: colors.border },
  modelChipActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  modelChipText: { fontSize: 11, color: colors.muted },
  modelChipTextActive: { color: colors.white, fontWeight: '600' },
  messages: { padding: 12, paddingBottom: 4 },
  bubble: { maxWidth: '85%', borderRadius: 16, paddingHorizontal: 14, paddingVertical: 10, marginBottom: 10 },
  userBubble: { backgroundColor: colors.brand, alignSelf: 'flex-end' },
  aiBubble: { backgroundColor: colors.card, alignSelf: 'flex-start', borderWidth: 1, borderColor: colors.border },
  bubbleText: { fontSize: 15, color: colors.text, lineHeight: 22 },
  userText: { color: colors.white },
  modelLabel: { fontSize: 10, color: colors.muted, marginBottom: 4 },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingTop: 60 },
  emptyText: { color: colors.muted, fontSize: 14 },
  errorBar: { backgroundColor: 'rgba(239,68,68,0.1)', borderTopWidth: 1, borderTopColor: 'rgba(239,68,68,0.3)', padding: 8 },
  errorText: { color: '#f87171', fontSize: 12, textAlign: 'center' },
  inputRow: { flexDirection: 'row', alignItems: 'flex-end', padding: 10, borderTopWidth: 1, borderTopColor: colors.border, gap: 8 },
  input: { flex: 1, backgroundColor: colors.card, borderRadius: 20, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 14, paddingVertical: 10, color: colors.text, fontSize: 15, maxHeight: 120 },
  sendBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' },
  sendBtnStreaming: { backgroundColor: '#ef4444' },
  sendBtnText: { color: colors.white, fontSize: 18, fontWeight: '700' },
})
