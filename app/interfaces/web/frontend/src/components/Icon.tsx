import {
  Activity, Camera, Cat, Cctv, Check, ChevronDown, ChevronUp, Cuboid, Eye, EyeOff, House,
  LockKeyhole, Menu, MessagesSquare, Minus, Palette, Pause, Pencil, Play, PlugZap, Plus,
  QrCode, RotateCcw, RotateCw, ScrollText, Search, Settings, User, Users, Utensils, Wrench, X,
} from "lucide-react"
import type { LucideIcon } from "lucide-react"

export type IconName =
  | "activity" | "camera" | "cat" | "cctv" | "check" | "chevron-down" | "chevron-up" | "cuboid"
  | "eye" | "eye-off" | "house" | "lock-keyhole" | "menu" | "messages-square" | "minus"
  | "palette" | "pause" | "pencil" | "play" | "plug-zap" | "plus" | "qr-code" | "rotate-ccw" | "rotate-cw" | "search" | "scroll"
  | "settings" | "user" | "users" | "utensils" | "wrench" | "x"

const iconComponents = {
  activity: Activity,
  camera: Camera,
  cat: Cat,
  cctv: Cctv,
  check: Check,
  "chevron-down": ChevronDown,
  "chevron-up": ChevronUp,
  cuboid: Cuboid,
  eye: Eye,
  "eye-off": EyeOff,
  house: House,
  "lock-keyhole": LockKeyhole,
  menu: Menu,
  "messages-square": MessagesSquare,
  minus: Minus,
  palette: Palette,
  pause: Pause,
  pencil: Pencil,
  play: Play,
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
