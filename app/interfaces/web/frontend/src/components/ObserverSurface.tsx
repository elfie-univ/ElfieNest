import { useEffect, useRef } from "react"

import { Button } from "@/components/ui/button"
import { useOptionalObserver } from "../stores/observer"
import { Icon } from "./Icon"

type ObserverSurfaceProps =
  | { readonly kind: "room"; readonly roomId: string; readonly title: string }
  | { readonly elfieId: string; readonly kind: "elfie"; readonly title: string }

export function ObserverSurface(props: ObserverSurfaceProps) {
  const observer = useOptionalObserver()
  const surfaceRef = useRef<HTMLDivElement | null>(null)
  const isRoom = props.kind === "room"
  const open = (): void => {
    if (observer === null) return
    observer.attach(surfaceRef.current)
    if (isRoom) {
      void observer.openRoom(props.roomId)
      return
    }
    void observer.openElfie(props.elfieId)
  }

  useEffect(() => {
    if (observer === null) return undefined
    observer.attach(surfaceRef.current)
    return (): void => observer.detach()
  }, [observer?.attach, observer?.detach])

  const statusCopy = isRoom
    ? "拖动以自由查看房间，滚轮或双指缩放。"
    : "拖动环绕精灵，滚轮或双指缩放。"
  const status = observer?.status ?? "fallback"
  const entityCount = Object.keys(observer?.entities ?? {}).length
  return <section aria-label={props.title} className="observer-surface">
    <div className="observer-surface__head"><div><strong>{props.title}</strong><small>{statusCopy}</small></div>{status === "idle" ? <Button onClick={open} type="button"><Icon name="cuboid" size={16} />进入 3D</Button> : <Button onClick={() => observer?.detach()} type="button" variant="outline">结束观察</Button>}</div>
    <div className={status === "ready" || status === "loading" ? "observer-surface__viewport" : "observer-surface__fallback"} ref={surfaceRef}>
      {status === "idle" ? <p>3D 将在首次打开时加载；聊天与管理不会因此等待。</p> : null}
      {status === "loading" ? <p>正在建立本地观察视角…</p> : null}
      {status === "fallback" ? <><p>当前设备无法运行 3D 观察，已保留语义状态和页面操作。</p><p>{entityCount > 0 ? `当前可见 ${entityCount} 位精灵。` : "可继续使用聊天、资料和房间管理。"}</p>{observer !== null ? <Button onClick={open} type="button">重试 3D</Button> : null}</> : null}
    </div>
  </section>
}
