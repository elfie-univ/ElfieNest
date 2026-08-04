import { useCallback, useEffect } from "react"

import { navigate, replaceLocation, useAppLocation } from "../stores/history"
import {
  buildChatViewPath,
  parseChatViewState,
  type ChatViewPathTarget,
  type ChatViewState,
} from "./chat-view-state"

export type ChatPane = "chats" | "elfies"

type ChatViewController = {
  readonly state: ChatViewState
  readonly activePane: ChatPane
  readonly selectedId: string | null
  readonly mobileDetail: boolean
  readonly go: (target: ChatViewPathTarget) => void
  readonly correct: (target: ChatViewPathTarget) => void
}

export function useChatView(): ChatViewController {
  const location = useAppLocation()
  const state = parseChatViewState(location.search)
  const canonicalPath = buildChatViewPath(state)
  const currentPath = `/chat${location.search}`

  useEffect(() => {
    if (canonicalPath !== currentPath) replaceLocation(canonicalPath)
  }, [canonicalPath, currentPath])

  const go = useCallback((target: ChatViewPathTarget): void => {
    navigate(buildChatViewPath(target))
  }, [location.search])

  const correct = useCallback((target: ChatViewPathTarget): void => {
    replaceLocation(buildChatViewPath(target))
  }, [location.search])

  return {
    state,
    activePane: state.view === "conversation" ? "chats" : "elfies",
    selectedId: state.view === "elfies" ? null : state.elfie,
    mobileDetail: state.view !== "elfies",
    go,
    correct,
  }
}
