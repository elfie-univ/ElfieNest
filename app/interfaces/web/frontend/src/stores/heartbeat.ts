import { useEffect } from "react"

import { heartbeat, type ClientUser } from "../api/client"

const HEARTBEAT_INTERVAL_MS = 30_000

export function usePresenceHeartbeat(user: ClientUser | null): void {
  useEffect(() => {
    if (user === null) return undefined
    let timer: number | undefined
    let stopped = false
    const csrfToken = user.csrf_token ?? ""

    const send = (): void => {
      if (stopped || document.hidden || csrfToken === "") return
      void heartbeat(csrfToken)
    }
    const schedule = (): void => {
      window.clearInterval(timer)
      if (!document.hidden) {
        send()
        timer = window.setInterval(send, HEARTBEAT_INTERVAL_MS)
      }
    }
    document.addEventListener("visibilitychange", schedule)
    schedule()
    return () => {
      stopped = true
      window.clearInterval(timer)
      document.removeEventListener("visibilitychange", schedule)
    }
  }, [user])
}
