import { ObservationMonitor } from "../components/ObservationMonitor"
import { useSession } from "../stores/session"

type MonitorPageProps = {
  readonly roomId?: string
}

export function MonitorPage({ roomId = "local-nest" }: MonitorPageProps) {
  const { user, loading } = useSession()
  if (loading) return <main className="page"><p className="empty">正在验证会话…</p></main>
  if (user?.role !== "owner") { window.location.assign(user === null ? "/login?next=/monitor" : "/chat"); return <main /> }
  return <main className="monitor-page"><ObservationMonitor roomId={roomId} /></main>
}
