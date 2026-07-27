import { useSyncExternalStore } from "react"

export type AppLocation = {
  readonly pathname: string
  readonly search: string
}

const LOCATION_EVENT = "elfienest:location-change"

function readLocation(): AppLocation {
  return { pathname: window.location.pathname, search: window.location.search }
}

function locationKey(): string {
  return `${window.location.pathname}${window.location.search}`
}

export function subscribeToLocation(listener: (location: AppLocation) => void): () => void {
  const notify = (): void => listener(readLocation())
  window.addEventListener("popstate", notify)
  window.addEventListener(LOCATION_EVENT, notify)
  return (): void => {
    window.removeEventListener("popstate", notify)
    window.removeEventListener(LOCATION_EVENT, notify)
  }
}

export function navigate(path: string): void {
  window.history.pushState({}, "", path)
  window.dispatchEvent(new Event(LOCATION_EVENT))
}

export function useAppLocation(): AppLocation {
  const key = useSyncExternalStore(
    (listener) => subscribeToLocation(() => listener()),
    locationKey,
    locationKey,
  )
  const questionMark = key.indexOf("?")
  return questionMark === -1
    ? { pathname: key, search: "" }
    : { pathname: key.slice(0, questionMark), search: key.slice(questionMark) }
}

export function interceptProductNavigation(event: MouseEvent): void {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return
  const target = event.target
  if (!(target instanceof Element)) return
  const anchor = target.closest("a[href]")
  if (!(anchor instanceof HTMLAnchorElement)) return
  const url = new URL(anchor.href, window.location.origin)
  if (url.origin !== window.location.origin || (url.pathname !== "/chat" && url.pathname !== "/manage")) return
  event.preventDefault()
  navigate(`${url.pathname}${url.search}${url.hash}`)
}
