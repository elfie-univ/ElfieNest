import { useTranslation } from "react-i18next"

import { ObservationMonitor } from "../components/ObservationMonitor"
import { useSession } from "../stores/session"
import { isManagerRole } from "../api/roles"

type MonitorPageProps = {
  readonly roomId?: string
}

export function MonitorPage({ roomId = "local-nest" }: MonitorPageProps) {
  const { t } = useTranslation("monitor")
  const { user, loading } = useSession()
  if (loading) return <main className="page"><p className="empty">{t("session.verifying")}</p></main>
  if (user === null || !isManagerRole(user.role)) { window.location.assign(user === null ? "/login?next=/monitor" : "/chat"); return <main /> }
  return <main className="monitor-page"><ObservationMonitor roomId={roomId} /></main>
}
