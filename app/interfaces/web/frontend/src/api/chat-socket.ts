import { z } from "zod"

import { ChatMessageSchema } from "./client"
import { AccountRoleSchema } from "./roles"

const ReadyEventSchema = z.object({ event: z.literal("ready"), principal: z.object({ role: AccountRoleSchema, account_id: z.string() }) })
const MessageEventSchema = z.object({ event: z.literal("message"), message: ChatMessageSchema })
const ErrorEventSchema = z.object({ event: z.literal("error"), detail: z.string() })
const ChatSocketEventSchema = z.discriminatedUnion("event", [ReadyEventSchema, MessageEventSchema, ErrorEventSchema])

export type ChatSocketEvent = z.infer<typeof ChatSocketEventSchema>
export type ChatSocketStatus = "connecting" | "online" | "offline"
const RECONNECT_DELAY_MILLISECONDS = 1_000

export function parseChatSocketEvent(payload: unknown): ChatSocketEvent { return ChatSocketEventSchema.parse(payload) }

type ChatSocketCallbacks = { readonly onEvent: (event: ChatSocketEvent) => void; readonly onStatus: (status: ChatSocketStatus) => void }

export class ChatSocket {
  private socket: WebSocket | null = null
  private reconnectTimer: number | null = null
  private explicitlyClosed = false

  public constructor(private readonly callbacks: ChatSocketCallbacks) {}

  public connect(): void {
    this.explicitlyClosed = false
    this.clearReconnectTimer()
    this.disposeSocket()
    this.open()
  }

  private open(): void {
    if (this.explicitlyClosed) return
    this.callbacks.onStatus("connecting")
    const scheme = window.location.protocol === "https:" ? "wss" : "ws"
    const socket = new WebSocket(`${scheme}://${window.location.host}/api/v1/ws/chat`)
    this.socket = socket
    socket.addEventListener("open", () => {
      if (this.socket !== socket) return
      this.clearReconnectTimer()
      this.callbacks.onStatus("online")
    })
    socket.addEventListener("close", () => {
      if (this.socket !== socket) return
      this.socket = null
      this.callbacks.onStatus("offline")
      this.scheduleReconnect()
    })
    socket.addEventListener("message", (event) => {
      const payload = parsePayload(event.data)
      if (payload === null) { this.callbacks.onEvent({ event: "error", detail: "" }); return }
      try {
        this.callbacks.onEvent(parseChatSocketEvent(payload))
      } catch (error: unknown) {
        if (error instanceof z.ZodError) {
          this.callbacks.onEvent({ event: "error", detail: "" })
          return
        }
        throw error
      }
    })
  }

  public send(elfieId: string, text: string): boolean {
    if (this.socket?.readyState !== WebSocket.OPEN) return false
    this.socket.send(JSON.stringify({ event: "user_message", elfie_id: elfieId, text }))
    return true
  }

  public close(): void {
    this.explicitlyClosed = true
    this.clearReconnectTimer()
    this.disposeSocket()
  }

  private scheduleReconnect(): void {
    if (this.explicitlyClosed || this.reconnectTimer !== null) return
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null
      this.open()
    }, RECONNECT_DELAY_MILLISECONDS)
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) window.clearTimeout(this.reconnectTimer)
    this.reconnectTimer = null
  }

  private disposeSocket(): void {
    const current = this.socket
    this.socket = null
    current?.close()
  }
}

function parsePayload(raw: unknown): unknown | null {
  if (typeof raw !== "string") return null
  try { return JSON.parse(raw) } catch (error: unknown) { if (error instanceof SyntaxError) return null; throw error }
}
