import React, { useState } from 'react'
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
} from 'react-native'
import { useAppStore } from '../../store/appStore'
import { colors } from '../../theme'

const SECTION_LABELS: Record<string, string> = {
  harness: 'Companion',
  user: 'Profile',
  config: 'Config',
  session_state: 'Session',
}

export default function VaultSections() {
  const { session, activeSection, setActiveSection, setPendingEdit, pendingEdits } = useAppStore()
  const [editing, setEditing] = useState<string | null>(null)

  if (!session) return null

  const sections = Object.keys(session.sections)

  function getContent(name: string) {
    return pendingEdits[name] ?? session!.sections[name] ?? ''
  }

  function handleEdit(name: string) {
    setEditing(name)
  }

  function handleSave(name: string, value: string) {
    setPendingEdit(name, value)
    setEditing(null)
  }

  return (
    <View style={styles.container}>
      {/* Section tabs */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tabs} contentContainerStyle={styles.tabsContent}>
        {sections.map((name) => (
          <TouchableOpacity
            key={name}
            style={[styles.tab, activeSection === name && styles.tabActive]}
            onPress={() => { setActiveSection(name); setEditing(null) }}
          >
            <Text style={[styles.tabText, activeSection === name && styles.tabTextActive]}>
              {SECTION_LABELS[name] ?? name}
              {pendingEdits[name] !== undefined ? ' •' : ''}
            </Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {/* Section content */}
      <View style={styles.content}>
        {editing === activeSection ? (
          <SectionEditor
            name={activeSection}
            initialValue={getContent(activeSection)}
            onSave={(v) => handleSave(activeSection, v)}
            onCancel={() => setEditing(null)}
          />
        ) : (
          <>
            <ScrollView style={styles.preview}>
              <Text style={styles.previewText}>
                {getContent(activeSection) || '(empty)'}
              </Text>
            </ScrollView>
            <TouchableOpacity
              style={styles.editBtn}
              onPress={() => handleEdit(activeSection)}
            >
              <Text style={styles.editBtnText}>Edit</Text>
            </TouchableOpacity>
          </>
        )}
      </View>
    </View>
  )
}

function SectionEditor({
  name,
  initialValue,
  onSave,
  onCancel,
}: {
  name: string
  initialValue: string
  onSave: (v: string) => void
  onCancel: () => void
}) {
  const [value, setValue] = useState(initialValue)

  return (
    <View style={styles.editorContainer}>
      <TextInput
        style={styles.editor}
        value={value}
        onChangeText={setValue}
        multiline
        autoFocus
        textAlignVertical="top"
        autoCapitalize="none"
        autoCorrect={false}
      />
      <View style={styles.editorActions}>
        <TouchableOpacity style={styles.cancelBtn} onPress={onCancel}>
          <Text style={styles.cancelBtnText}>Cancel</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.saveBtn} onPress={() => onSave(value)}>
          <Text style={styles.saveBtnText}>Save</Text>
        </TouchableOpacity>
      </View>
    </View>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  tabs: { borderBottomWidth: 1, borderBottomColor: colors.border, flexGrow: 0 },
  tabsContent: { paddingHorizontal: 8, paddingVertical: 6, gap: 4 },
  tab: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8 },
  tabActive: { backgroundColor: colors.card, borderWidth: 1, borderColor: colors.brand },
  tabText: { fontSize: 12, color: colors.muted, fontWeight: '500' },
  tabTextActive: { color: colors.brandLight },
  content: { flex: 1 },
  preview: { flex: 1, padding: 12 },
  previewText: { color: colors.text, fontSize: 13, lineHeight: 20, fontFamily: 'monospace' },
  editBtn: { margin: 10, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: colors.border, alignItems: 'center' },
  editBtnText: { color: colors.muted, fontSize: 13 },
  editorContainer: { flex: 1, padding: 8 },
  editor: { flex: 1, backgroundColor: colors.card, borderRadius: 8, borderWidth: 1, borderColor: colors.brand, padding: 10, color: colors.text, fontSize: 13, fontFamily: 'monospace', lineHeight: 20 },
  editorActions: { flexDirection: 'row', gap: 8, marginTop: 8 },
  cancelBtn: { flex: 1, paddingVertical: 10, borderRadius: 8, borderWidth: 1, borderColor: colors.border, alignItems: 'center' },
  cancelBtnText: { color: colors.muted, fontSize: 13 },
  saveBtn: { flex: 1, paddingVertical: 10, borderRadius: 8, backgroundColor: colors.brand, alignItems: 'center' },
  saveBtnText: { color: colors.white, fontWeight: '600', fontSize: 13 },
})
