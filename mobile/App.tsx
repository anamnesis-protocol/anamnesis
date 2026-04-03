import React, { useEffect } from 'react'
import { View, ActivityIndicator, StyleSheet } from 'react-native'
import { StatusBar } from 'expo-status-bar'
import { useAppStore } from './src/store/appStore'
import { setBaseUrl } from './src/api/client'
import ConnectScreen from './src/screens/ConnectScreen'
import SessionScreen from './src/screens/SessionScreen'
import { colors } from './src/theme'

export default function App() {
  const { session, apiBaseUrl } = useAppStore()

  // Sync persisted API URL to the client on startup
  useEffect(() => {
    setBaseUrl(apiBaseUrl)
  }, [apiBaseUrl])

  return (
    <View style={styles.root}>
      <StatusBar style="light" backgroundColor={colors.bg} />
      {session ? <SessionScreen /> : <ConnectScreen />}
    </View>
  )
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
})
