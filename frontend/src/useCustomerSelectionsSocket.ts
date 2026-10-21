import { useEffect, useRef } from 'react'
import { DEMO_AUTH_EXPIRED_EVENT, restoreDemoSession } from './demoAuth'
import { WS_ORIGIN } from './apiConfig'

type Options = {
  sessionId: number | null
  onRefresh: () => Promise<void>
  onSessionEnded: () => void
}

const NOTIFICATION_DEBOUNCE_MS = 100
const FALLBACK_REFRESH_MS = 60_000
const MAX_RECONNECT_DELAY_MS = 30_000

export function useCustomerSelectionsSocket({ sessionId, onRefresh, onSessionEnded }: Options) {
  const onRefreshRef = useRef(onRefresh)
  const onSessionEndedRef = useRef(onSessionEnded)

  useEffect(() => { onRefreshRef.current = onRefresh }, [onRefresh])
  useEffect(() => { onSessionEndedRef.current = onSessionEnded }, [onSessionEnded])

  useEffect(() => {
    if (sessionId === null) return

    let socket: WebSocket | null = null
    let stopped = false
    let reconnectAttempt = 0
    let reconnectTimer: number | undefined
    let debounceTimer: number | undefined
    let refreshRunning = false
    let refreshQueued = false

    const refreshLatest = async () => {
      refreshQueued = true
      if (refreshRunning) return
      refreshRunning = true
      try {
        while (refreshQueued && !stopped) {
          refreshQueued = false
          await onRefreshRef.current()
        }
      } finally {
        refreshRunning = false
      }
    }

    const scheduleRefresh = () => {
      if (debounceTimer !== undefined) window.clearTimeout(debounceTimer)
      debounceTimer = window.setTimeout(() => {
        debounceTimer = undefined
        void refreshLatest()
      }, NOTIFICATION_DEBOUNCE_MS)
    }

    const connect = () => {
      if (stopped) return
      const token = localStorage.getItem('customer_token')
      if (!token) return

      socket = new WebSocket(`${WS_ORIGIN}/ws/customer/selections`)
      socket.onopen = () => {
        socket?.send(JSON.stringify({ type: 'auth', token }))
      }
      socket.onmessage = (event) => {
        let message: { type?: string; session_id?: number }
        try {
          message = JSON.parse(String(event.data))
        } catch {
          return
        }
        if (message.session_id !== sessionId) return
        if (message.type === 'authenticated') {
          reconnectAttempt = 0
          void refreshLatest()
        } else if (message.type === 'selections_changed') {
          scheduleRefresh()
        } else if (message.type === 'session_ended') {
          stopped = true
          onSessionEndedRef.current()
        }
      }
      socket.onclose = async (event) => {
        socket = null
        if (stopped) return
        if (event.code === 1008 || event.code === 4001) {
          stopped = true
          try {
            if (await restoreDemoSession()) onSessionEndedRef.current()
            else window.dispatchEvent(new Event(DEMO_AUTH_EXPIRED_EVENT))
          } catch {
            // A network failure is not proof of authentication expiry. Let the
            // fallback HTTP refresh surface the connectivity error.
          }
          return
        }
        const baseDelay = Math.min(1000 * (2 ** reconnectAttempt), MAX_RECONNECT_DELAY_MS)
        const delay = Math.round(baseDelay * (0.8 + Math.random() * 0.4))
        reconnectAttempt += 1
        reconnectTimer = window.setTimeout(connect, delay)
      }
    }

    connect()
    const fallbackTimer = window.setInterval(() => { void refreshLatest() }, FALLBACK_REFRESH_MS)

    return () => {
      stopped = true
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer)
      if (debounceTimer !== undefined) window.clearTimeout(debounceTimer)
      window.clearInterval(fallbackTimer)
      socket?.close(1000, 'Component unmounted')
    }
  }, [sessionId])
}
