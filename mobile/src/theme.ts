import { StyleSheet } from 'react-native'

export const colors = {
  bg: '#0f1117',
  card: '#1a1d27',
  inputBg: '#12141e',
  border: '#2a2d3d',
  brand: '#6366f1',
  brandLight: '#818cf8',
  text: '#e2e8f0',
  muted: '#64748b',
  subtle: '#334155',
  white: '#ffffff',
  success: '#22c55e',
  error: '#ef4444',
}

// Shared utility styles
export const s = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center' },
  flex1: { flex: 1 },
  mono: { fontFamily: 'monospace' },
})
