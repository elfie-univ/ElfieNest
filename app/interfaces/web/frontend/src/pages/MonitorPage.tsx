import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { ownerRooms } from "../api/client"
import { MobileAccessDialog } from "../components/MobileAccessDialog"
import { MonitorRail } from "../components/MonitorRail"
import { ObservationMonitor } from "../components/ObservationMonitor"
import { useSession } from "../stores/session"
import { canAccessMonitor } from "../api/roles"

type MonitorPageProps = {
  readonly roomId?: string
}

export function MonitorPage({ roomId = "local-nest" }: MonitorPageProps) {
  const { t } = useTranslation("monitor")
  const { refresh, user, loading } = useSession()
  const [roomReady, setRoomReady] = useState(false)
  const [immersive, setImmersive] = useState(false)
  const [roomLoadFailed, setRoomLoadFailed] = useState(false)
  const [showMobileAccess, setShowMobileAccess] = useState(false)
  const authorized = user !== null && canAccessMonitor(user.role)
  useEffect(() => {
    if (loading || !authorized) return undefined
    let active = true
    setRoomReady(false)
    setRoomLoadFailed(false)
    void ownerRooms().then((rooms) => {
      if (!active) return
      const room = rooms.find((candidate) => candidate.id === roomId)
      if (room === undefined) {
        setRoomLoadFailed(true)
        return
      }
      setRoomReady(true)
    }).catch(() => {
      if (active) setRoomLoadFailed(true)
    })
    return (): void => { active = false }
  }, [authorized, loading, roomId])
  if (loading) return <main className="page"><p className="empty">{t("session.verifying")}</p></main>
  if (user === null || !canAccessMonitor(user.role)) { window.location.assign(user === null ? "/login?next=/monitor" : "/chat"); return <main /> }
  return <main className={immersive ? "monitor-page monitor-page--immersive" : "monitor-page"}>
    {!immersive ? <MonitorRail onMobileAccess={() => setShowMobileAccess(true)} onToggleImmersive={() => setImmersive(true)} onUpdated={refresh} user={user} /> : null}
    {!roomReady
      ? <p className="empty monitor-page__status">{roomLoadFailed ? t("status.offline") : t("surface.loading")}</p>
      : <ObservationMonitor immersive={immersive} mode="standalone" onExitImmersive={() => setImmersive(false)} roomId={roomId} />}
    {showMobileAccess ? <MobileAccessDialog onClose={() => setShowMobileAccess(false)} targetPath="/monitor" /> : null}
  </main>
}
