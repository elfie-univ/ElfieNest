import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { ownerRooms } from "../api/client"
import { MobileAccessDialog } from "../components/MobileAccessDialog"
import { MonitorRail } from "../components/MonitorRail"
import { ObservationMonitor } from "../components/ObservationMonitor"
import { useSession } from "../stores/session"
import { isManagerRole } from "../api/roles"

type MonitorPageProps = {
  readonly roomId?: string
}

export function MonitorPage({ roomId = "local-nest" }: MonitorPageProps) {
  const { t } = useTranslation("monitor")
  const { refresh, user, loading } = useSession()
  const [bedCount, setBedCount] = useState<number | null>(null)
  const [immersive, setImmersive] = useState(false)
  const [roomLoadFailed, setRoomLoadFailed] = useState(false)
  const [showMobileAccess, setShowMobileAccess] = useState(false)
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
  if (user === null || !isManagerRole(user.role)) { window.location.assign(user === null ? "/login?next=/monitor" : "/chat"); return <main /> }
  return <main className={immersive ? "monitor-page monitor-page--immersive" : "monitor-page"}>
    {!immersive ? <MonitorRail onMobileAccess={() => setShowMobileAccess(true)} onToggleImmersive={() => setImmersive(true)} onUpdated={refresh} user={user} /> : null}
    {bedCount === null
      ? <p className="empty monitor-page__status">{roomLoadFailed ? t("status.offline") : t("surface.loading")}</p>
      : <ObservationMonitor bedCount={bedCount} immersive={immersive} mode="standalone" onExitImmersive={() => setImmersive(false)} roomId={roomId} />}
    {showMobileAccess ? <MobileAccessDialog onClose={() => setShowMobileAccess(false)} targetPath="/monitor" /> : null}
  </main>
}
