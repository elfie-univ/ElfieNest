import { useCallback, useEffect, useMemo, useRef } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { useOptionalObserver } from "../stores/observer"
import { createObserverWorldConfig, type ObserverWorldConfig } from "../stores/observer-protocol"
import { Icon } from "./Icon"

type ObserverSurfaceProps =
  | { readonly autoStart?: boolean; readonly bedCount: number; readonly kind: "room"; readonly roomId: string; readonly showHeader?: boolean; readonly title: string }
  | { readonly autoStart?: boolean; readonly elfieId: string; readonly kind: "elfie"; readonly showHeader?: boolean; readonly title: string }

export function ObserverSurface(props: ObserverSurfaceProps) {
  const { t } = useTranslation("monitor")
  const observer = useOptionalObserver()
  const surfaceRef = useRef<HTMLDivElement | null>(null)
  const autoStartedRef = useRef(false)
  const isRoom = props.kind === "room"
  const roomId = isRoom ? props.roomId : null
  const elfieId = isRoom ? null : props.elfieId
  const bedCount = isRoom ? props.bedCount : null
  const worldConfig = useMemo<ObserverWorldConfig | null>(
    () => roomId !== null && bedCount !== null ? createObserverWorldConfig(roomId, bedCount) : null,
    [bedCount, roomId],
  )
  const open = useCallback((): void => {
    if (observer === null) return
    observer.attach(surfaceRef.current)
    if (roomId !== null) {
      if (worldConfig === null) return
      void observer.openRoom(roomId, worldConfig)
      return
    }
    if (elfieId !== null) void observer.openElfie(elfieId)
  }, [elfieId, observer, roomId, worldConfig])

  useEffect(() => {
    if (observer === null) return undefined
    observer.attach(surfaceRef.current)
    return (): void => observer.detach()
  }, [observer?.attach, observer?.detach])

  useEffect(() => {
    if (!props.autoStart || autoStartedRef.current) return
    autoStartedRef.current = true
    open()
  }, [open, props.autoStart])

  useEffect(() => {
    if (!props.autoStart || !autoStartedRef.current || observer === null || worldConfig === null) return
    observer.configureRoom(worldConfig)
  }, [observer?.configureRoom, props.autoStart, worldConfig])

  const statusCopy = isRoom
    ? t("surface.roomHint")
    : t("surface.elfieHint")
  const status = observer?.status ?? "fallback"
  const fallbackReason = observer?.fallbackReason ?? "disabled"
  const entityCount = Object.keys(observer?.entities ?? {}).length
  const showHeader = props.showHeader ?? true
  const fallbackTitle = fallbackReason === "insecure-context"
    ? t("surface.fallback.insecureTitle")
    : fallbackReason === "unsupported-device"
      ? t("surface.fallback.unsupportedTitle")
      : t("surface.fallback.unavailableTitle")
  const fallbackDetail = fallbackReason === "insecure-context"
    ? t("surface.fallback.insecureDetail")
    : entityCount > 0
      ? t("surface.fallback.entityCount", { count: entityCount })
      : t("surface.fallback.continue")
  return <section aria-label={props.title} className="observer-surface">
    {showHeader ? <div className="observer-surface__head"><div><strong>{props.title}</strong><small>{statusCopy}</small></div>{status === "idle" ? <Button onClick={open} type="button"><Icon name="cuboid" size={16} />{t("surface.enter")}</Button> : <Button onClick={() => observer?.detach()} type="button" variant="outline">{t("surface.end")}</Button>}</div> : null}
    <div className={status === "ready" || status === "loading" ? "observer-surface__viewport" : "observer-surface__fallback"} ref={surfaceRef}>
      {status === "idle" ? <p>{t("surface.idle")}</p> : null}
      {status === "loading" ? <p>{t("surface.loading")}</p> : null}
      {status === "fallback" ? <><p>{fallbackTitle}</p><p>{fallbackDetail}</p>{observer !== null && fallbackReason !== "insecure-context" ? <Button onClick={open} type="button">{t("surface.retry")}</Button> : null}</> : null}
    </div>
  </section>
}
