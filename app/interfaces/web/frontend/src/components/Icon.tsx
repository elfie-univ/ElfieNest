import {
  Activity, Cat, Check, ChevronDown, ChevronUp, Cuboid, House, LockKeyhole, Menu,
  MessagesSquare, Palette, Pencil, PlugZap, Plus, QrCode, RotateCcw, RotateCw, Search,
  ScrollText, Settings, Minus, User, Users, Utensils, Wrench, X, Camera
} from "lucide-react"
import type { LucideIcon } from "lucide-react"

export type IconName =
  | "activity" | "camera" | "cat" | "check" | "chevron-down" | "chevron-up" | "cuboid"
  | "house" | "lock-keyhole" | "menu" | "messages-square" | "minus" | "palette" | "pencil"
  | "plug-zap" | "plus" | "qr-code" | "rotate-ccw" | "rotate-cw" | "search" | "scroll"
  | "settings" | "user" | "users" | "utensils" | "wrench" | "x"

const iconComponents = {
  activity: Activity,
  camera: Camera,
  cat: Cat,
  check: Check,
  "chevron-down": ChevronDown,
  "chevron-up": ChevronUp,
  cuboid: Cuboid,
  house: House,
  "lock-keyhole": LockKeyhole,
  menu: Menu,
  "messages-square": MessagesSquare,
  minus: Minus,
  palette: Palette,
  pencil: Pencil,
  "plug-zap": PlugZap,
  plus: Plus,
  "qr-code": QrCode,
  "rotate-ccw": RotateCcw,
  "rotate-cw": RotateCw,
  search: Search,
  scroll: ScrollText,
  settings: Settings,
  user: User,
  users: Users,
  utensils: Utensils,
  wrench: Wrench,
  x: X
} satisfies Record<IconName, LucideIcon>

type IconProps = {
  readonly name: IconName
  readonly size?: number
}

export function Icon({ name, size = 20 }: IconProps) {
  const LucideIcon = iconComponents[name]
  return <LucideIcon aria-hidden="true" size={size} strokeWidth={1.8} />
}
