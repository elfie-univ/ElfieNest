import type { KeyboardEvent, PointerEvent, WheelEvent } from "react"
import { useEffect, useRef, useState } from "react"

const MIN_SCALE = 0.72
const MAX_SCALE = 1.8
const ZOOM_STEP = 0.1
const KEYBOARD_ORBIT_STEP = 8

type Point = {
  readonly x: number
  readonly y: number
}

export type AppearanceInteraction = {
  readonly onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => void
  readonly onPointerDown: (event: PointerEvent<HTMLDivElement>) => void
  readonly onPointerEnd: (event: PointerEvent<HTMLDivElement>) => void
  readonly onPointerLost: (event: PointerEvent<HTMLDivElement>) => void
  readonly onPointerMove: (event: PointerEvent<HTMLDivElement>) => void
  readonly onWheel: (event: WheelEvent<HTMLDivElement>) => void
  readonly reset: () => void
  readonly scale: number
  readonly yaw: number
}

export function useAppearanceInteraction(active: boolean): AppearanceInteraction {
  const [scale, setScale] = useState(1)
  const [yaw, setYaw] = useState(0)
  const pointersRef = useRef(new Map<number, Point>())
  const lastPinchDistanceRef = useRef<number | null>(null)

  useEffect(() => {
    if (!active) {
      clearGesture()
    }
  }, [active])

  function updateScale(nextScale: number): void {
    setScale(Math.min(MAX_SCALE, Math.max(MIN_SCALE, nextScale)))
  }

  function updatePinchDistance(): void {
    lastPinchDistanceRef.current = pointerDistance(pointersRef.current)
  }

  function clearGesture(): void {
    pointersRef.current.clear()
    lastPinchDistanceRef.current = null
  }

  function reset(): void {
    setScale(1)
    setYaw(0)
    clearGesture()
  }

  function onPointerDown(event: PointerEvent<HTMLDivElement>): void {
    if (!active) {
      return
    }
    pointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY })
    if (typeof event.currentTarget.setPointerCapture === "function") {
      event.currentTarget.setPointerCapture(event.pointerId)
    }
    updatePinchDistance()
  }

  function onPointerMove(event: PointerEvent<HTMLDivElement>): void {
    const previous = pointersRef.current.get(event.pointerId)
    if (!active || previous === undefined) {
      return
    }
    pointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY })
    if (pointersRef.current.size === 1) {
      setYaw((currentYaw) => currentYaw + (event.clientX - previous.x) * 0.4)
      return
    }
    const distance = pointerDistance(pointersRef.current)
    const previousDistance = lastPinchDistanceRef.current
    if (distance !== null && previousDistance !== null && previousDistance > 0) {
      updateScale(scale * distance / previousDistance)
    }
    lastPinchDistanceRef.current = distance
  }

  function onPointerEnd(event: PointerEvent<HTMLDivElement>): void {
    pointersRef.current.delete(event.pointerId)
    if (typeof event.currentTarget.releasePointerCapture === "function"
      && event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
    updatePinchDistance()
  }

  function onPointerLost(event: PointerEvent<HTMLDivElement>): void {
    pointersRef.current.delete(event.pointerId)
    updatePinchDistance()
  }

  function onWheel(event: WheelEvent<HTMLDivElement>): void {
    if (!active) {
      return
    }
    event.preventDefault()
    updateScale(scale + (event.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP))
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    if (!active) {
      return
    }
    switch (event.key) {
      case "ArrowLeft":
        setYaw((currentYaw) => currentYaw - KEYBOARD_ORBIT_STEP)
        break
      case "ArrowRight":
        setYaw((currentYaw) => currentYaw + KEYBOARD_ORBIT_STEP)
        break
      case "+":
      case "=":
        updateScale(scale + ZOOM_STEP)
        break
      case "-":
        updateScale(scale - ZOOM_STEP)
        break
      case "Home":
        reset()
        break
      default:
        return
    }
    event.preventDefault()
  }

  return {
    onKeyDown,
    onPointerDown,
    onPointerEnd,
    onPointerLost,
    onPointerMove,
    onWheel,
    reset,
    scale,
    yaw,
  }
}

function pointerDistance(pointers: ReadonlyMap<number, Point>): number | null {
  if (pointers.size !== 2) {
    return null
  }
  const iterator = pointers.values()
  const first = iterator.next()
  const second = iterator.next()
  if (first.done || second.done) {
    return null
  }
  return Math.hypot(second.value.x - first.value.x, second.value.y - first.value.y)
}
