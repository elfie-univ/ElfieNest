import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react"

import { currentUser, type ClientUser } from "../api/client"
import { interceptProductNavigation } from "./history"
import { ObserverProvider } from "./observer"

type SessionState = {
  readonly user: ClientUser | null
  readonly loading: boolean
  readonly refresh: () => Promise<void>
  readonly refreshCsrfToken: () => Promise<string>
}
const SessionContext = createContext<SessionState | null>(null)

export function SessionProvider({ children }: { readonly children: ReactNode }) {
  const [user, setUser] = useState<ClientUser | null>(null)
  const [loading, setLoading] = useState(true)
  const refreshUser = useCallback(async (): Promise<ClientUser | null> => {
    try {
      const nextUser = await currentUser()
      setUser(nextUser)
      return nextUser
    } catch {
      setUser(null)
      return null
    } finally {
      setLoading(false)
    }
  }, [])
  const refresh = useCallback(async (): Promise<void> => {
    await refreshUser()
  }, [refreshUser])
  const refreshCsrfToken = useCallback(async (): Promise<string> => (
    (await refreshUser())?.csrf_token ?? ""
  ), [refreshUser])
  useEffect(() => { void refresh() }, [refresh])
  useEffect(() => {
    document.documentElement.dataset["theme"] = user?.theme_key ?? "warm-paper"
  }, [user])
  useEffect(() => {
    document.addEventListener("click", interceptProductNavigation)
    return (): void => document.removeEventListener("click", interceptProductNavigation)
  }, [])
  return <SessionContext.Provider value={{ user, loading, refresh, refreshCsrfToken }}><ObserverProvider csrfToken={user?.csrf_token ?? ""} enabled={user !== null}>{children}</ObserverProvider></SessionContext.Provider>
}

export function useSession(): SessionState {
  const state = useContext(SessionContext)
  if (state === null) throw new Error("SessionProvider is required")
  return state
}
