import { createContext, useContext, useEffect, useState, type ReactNode } from "react"

import { currentUser, type ClientUser } from "../api/client"
import { interceptProductNavigation } from "./history"
import { ObserverProvider } from "./observer"

type SessionState = { readonly user: ClientUser | null; readonly loading: boolean; readonly refresh: () => Promise<void> }
const SessionContext = createContext<SessionState | null>(null)

export function SessionProvider({ children }: { readonly children: ReactNode }) {
  const [user, setUser] = useState<ClientUser | null>(null)
  const [loading, setLoading] = useState(true)
  const refresh = async (): Promise<void> => {
    try { setUser(await currentUser()) } catch { setUser(null) } finally { setLoading(false) }
  }
  useEffect(() => { void refresh() }, [])
  useEffect(() => {
    document.documentElement.dataset["theme"] = user?.theme_key ?? "warm-paper"
  }, [user])
  useEffect(() => {
    document.addEventListener("click", interceptProductNavigation)
    return (): void => document.removeEventListener("click", interceptProductNavigation)
  }, [])
  return <SessionContext.Provider value={{ user, loading, refresh }}><ObserverProvider csrfToken={user?.csrf_token ?? ""} enabled={user !== null}>{children}</ObserverProvider></SessionContext.Provider>
}

export function useSession(): SessionState {
  const state = useContext(SessionContext)
  if (state === null) throw new Error("SessionProvider is required")
  return state
}
