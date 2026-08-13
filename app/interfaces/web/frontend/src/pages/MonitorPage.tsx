import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { ownerRooms } from "../api/client"
import { ObservationMonitor } from "../components/ObservationMonitor"
import { useSession } from "../stores/session"
import { isManagerRole } from "../api/roles"

type MonitorPageProps = {
  readonly roomId?: string
}

export function MonitorPage({ roomId = "local-nest" }: MonitorPageProps) {
  const { t } = useTranslation("monitor")
  const { user, loading } = useSession()
  const [bedCount, setBedCount] = useState<number | null>(null)
  const [roomLoadFailed, setRoomLoadFailed] = useState(false)
  const authorized = user !== null && isManagerRole(user.role)
  useEffect(() => {
    if (loading || !authorized) return undefined
    let active = true
    setBedCount(null)
    setRoomLoadFailed(false)
    void ownerRooms().then((rooms) => {
      if (!active) return
      const room = rooms.find((candidate) => candidate.id === roomId)
      if (room === undefined) {
        setRoomLoadFailed(true)
        return
      }
      setBedCount(room.desired_bed_count ?? Math.max(4, room.beds.length))
    }).catch(() => {
      if (active) setRoomLoadFailed(true)
    })
    return (): void => { active = false }
  }, [authorized, loading, roomId])
  if (loading) return <main className="page"><p className="empty">{t("session.verifying")}</p></main>
  if (!authorized) { window.location.assign(user === null ? "/login?next=/monitor" : "/chat"); return <main /> }
  if (bedCount === null) return <main className="monitor-page"><p className="empty">{roomLoadFailed ? t("status.offline") : t("surface.loading")}</p></main>
  return <main className="monitor-page"><ObservationMonitor bedCount={bedCount} roomId={roomId} showBackToManagement /></main>
}
