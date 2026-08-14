import {
  Activity, ArrowLeft, Camera, Cat, Cctv, Check, ChevronDown, ChevronUp, Cuboid, Eye, EyeOff, Globe2, House, Maximize2, PanelLeftOpen,
  LockKeyhole, LogOut, Menu, MessagesSquare, Minus, Palette, Pause, Pencil, Play, PlugZap, Plus,
  QrCode, RotateCcw, RotateCw, ScrollText, Search, Settings, User, Users, Utensils, Venus, Wrench, X, Mars,
} from "lucide-react"
import type { LucideIcon } from "lucide-react"

export type IconName =
  | "activity" | "arrow-left" | "camera" | "cat" | "cctv" | "check" | "chevron-down" | "chevron-up" | "cuboid"
  | "eye" | "eye-off" | "globe-2" | "house" | "lock-keyhole" | "log-out" | "maximize-2" | "menu" | "messages-square" | "minus" | "panel-left-open"
  | "palette" | "pause" | "pencil" | "play" | "plug-zap" | "plus" | "qr-code" | "rotate-ccw" | "rotate-cw" | "search" | "scroll"
  | "settings" | "user" | "users" | "utensils" | "venus" | "wrench" | "x" | "mars"

const iconComponents = {
  activity: Activity,
  "arrow-left": ArrowLeft,
  camera: Camera,
  cat: Cat,
  cctv: Cctv,
  check: Check,
  "chevron-down": ChevronDown,
  "chevron-up": ChevronUp,
  cuboid: Cuboid,
  eye: Eye,
  "eye-off": EyeOff,
  "globe-2": Globe2,
  house: House,
  "lock-keyhole": LockKeyhole,
  "log-out": LogOut,
  "maximize-2": Maximize2,
  menu: Menu,
  "messages-square": MessagesSquare,
  minus: Minus,
  "panel-left-open": PanelLeftOpen,
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
  venus: Venus,
  wrench: Wrench,
  x: X,
  mars: Mars,
} satisfies Record<IconName, LucideIcon>

type IconProps = {
  readonly name: IconName
  readonly size?: number
}

export function Icon({ name, size = 20 }: IconProps) {
  const LucideIcon = iconComponents[name]
  return <LucideIcon aria-hidden="true" size={size} strokeWidth={1.8} />
}
