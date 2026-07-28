import { useCallback, useEffect, useRef } from "react"

import { Button } from "@/components/ui/button"
import { useOptionalObserver } from "../stores/observer"
import { Icon } from "./Icon"

type ObserverSurfaceProps =
  | { readonly autoStart?: boolean; readonly kind: "room"; readonly roomId: string; readonly showHeader?: boolean; readonly title: string }
  | { readonly autoStart?: boolean; readonly elfieId: string; readonly kind: "elfie"; readonly showHeader?: boolean; readonly title: string }

export function ObserverSurface(props: ObserverSurfaceProps) {
  const observer = useOptionalObserver()
  const surfaceRef = useRef<HTMLDivElement | null>(null)
  const autoStartedRef = useRef(false)
  const isRoom = props.kind === "room"
  const roomId = isRoom ? props.roomId : null
  const elfieId = isRoom ? null : props.elfieId
  const open = useCallback((): void => {
    if (observer === null) return
    observer.attach(surfaceRef.current)
    if (roomId !== null) {
      void observer.openRoom(roomId)
      return
    }
    if (elfieId !== null) void observer.openElfie(elfieId)
  }, [elfieId, observer, roomId])

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

  const statusCopy = isRoom
    ? "拖动以自由查看房间，滚轮或双指缩放。"
    : "拖动环绕精灵，滚轮或双指缩放。"
  const status = observer?.status ?? "fallback"
  const fallbackReason = observer?.fallbackReason ?? "disabled"
  const entityCount = Object.keys(observer?.entities ?? {}).length
  const showHeader = props.showHeader ?? true
  const fallbackTitle = fallbackReason === "insecure-context"
    ? "手机浏览器需要安全连接才能打开 3D 房间观察。"
    : fallbackReason === "unsupported-device"
      ? "当前设备暂时无法运行 3D 房间观察。"
      : "当前无法运行 3D 观察。"
  const fallbackDetail = fallbackReason === "insecure-context"
    ? "请改用本机 localhost 访问，或把局域网地址配置为 HTTPS 后再打开预览。HTTP 的 192.168.* 地址会被浏览器拦截。"
    : entityCount > 0
      ? `当前可见 ${entityCount} 位精灵。`
      : "可继续使用聊天、资料和房间管理。"
  return <section aria-label={props.title} className="observer-surface">
    {showHeader ? <div className="observer-surface__head"><div><strong>{props.title}</strong><small>{statusCopy}</small></div>{status === "idle" ? <Button onClick={open} type="button"><Icon name="cuboid" size={16} />进入 3D</Button> : <Button onClick={() => observer?.detach()} type="button" variant="outline">结束观察</Button>}</div> : null}
    <div className={status === "ready" || status === "loading" ? "observer-surface__viewport" : "observer-surface__fallback"} ref={surfaceRef}>
      {status === "idle" ? <p>3D 将在首次打开时加载；聊天与管理不会因此等待。</p> : null}
      {status === "loading" ? <p>正在建立本地观察视角…</p> : null}
      {status === "fallback" ? <><p>{fallbackTitle}</p><p>{fallbackDetail}</p>{observer !== null && fallbackReason !== "insecure-context" ? <Button onClick={open} type="button">重试 3D</Button> : null}</> : null}
    </div>
  </section>
}
