import { z } from "zod"

import { ChatMessageSchema } from "./api"

const ReadyEventSchema = z.object({
  event: z.literal("ready"),
  principal: z.object({ role: z.union([z.literal("owner"), z.literal("user")]), username: z.string() })
})
const MessageEventSchema = z.object({ event: z.literal("message"), message: ChatMessageSchema })
const ErrorEventSchema = z.object({ event: z.literal("error"), detail: z.string() })
const ChatSocketEventSchema = z.discriminatedUnion("event", [ReadyEventSchema, MessageEventSchema, ErrorEventSchema])

export type ChatSocketEvent = z.infer<typeof ChatSocketEventSchema>
export type ChatSocketStatus = "connecting" | "online" | "offline"

export function parseChatSocketEvent(payload: unknown): ChatSocketEvent {
  return ChatSocketEventSchema.parse(payload)
}

type ChatSocketCallbacks = {
  readonly onEvent: (event: ChatSocketEvent) => void
  readonly onStatus: (status: ChatSocketStatus) => void
}

export class ChatSocket {
  private socket: WebSocket | null = null

  public constructor(private readonly callbacks: ChatSocketCallbacks) {}

  public connect(): void {
    this.close()
    this.callbacks.onStatus("connecting")
    const scheme = window.location.protocol === "https:" ? "wss" : "ws"
    const socket = new WebSocket(`${scheme}://${window.location.host}/api/v1/ws/chat`)
    this.socket = socket
    socket.addEventListener("open", () => this.callbacks.onStatus("online"))
    socket.addEventListener("close", () => {
      if (this.socket === socket) this.callbacks.onStatus("offline")
    })
    socket.addEventListener("message", (event) => {
      const payload = parsePayload(event.data)
      if (payload === null) {
        this.callbacks.onEvent({ event: "error", detail: "收到无法识别的实时消息" })
        return
      }
      const parsed = ChatSocketEventSchema.safeParse(payload)
      if (parsed.success) this.callbacks.onEvent(parsed.data)
      else this.callbacks.onEvent({ event: "error", detail: "收到不符合协议的实时消息" })
    })
  }

  public send(elfieId: string, text: string): boolean {
    if (this.socket?.readyState !== WebSocket.OPEN) return false
    this.socket.send(JSON.stringify({ event: "user_message", elfie_id: elfieId, text }))
    return true
  }

  public close(): void {
    const current = this.socket
    this.socket = null
    current?.close()
  }
}

function parsePayload(raw: unknown): unknown | null {
  if (typeof raw !== "string") return null
  try {
    return JSON.parse(raw)
  } catch (error: unknown) {
    if (error instanceof SyntaxError) return null
    throw error
  }
}
