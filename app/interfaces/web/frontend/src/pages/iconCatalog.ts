export const catalogIconNames = [
  "activity", "gauge", "chart", "scroll", "logs", "file", "bot", "sparkles", "wand",
  "house", "castle", "trees", "users", "contact", "user-settings", "plug", "cable",
  "network", "library", "boxes", "brain", "utensils", "cooking-pot", "wheat", "wrench",
  "shield", "key", "settings", "sliders", "panels", "cuboid", "box", "blocks", "message",
  "messages", "send", "qr", "scan", "phone", "profile"
] as const

export type CatalogIconName = typeof catalogIconNames[number]

export const iconCatalogGroupIds = [
  "monitor", "logs", "elfies", "nest", "users", "providers", "models", "foods", "tools",
  "system", "godot", "chat", "mobile", "profile",
] as const

export type IconCatalogGroupId = typeof iconCatalogGroupIds[number]

type IconChoice = {
  readonly id: CatalogIconName
  readonly label: string
  readonly url: string
}

export type IconCatalogGroup = {
  readonly id: IconCatalogGroupId
  readonly choices: readonly [IconChoice, IconChoice, IconChoice]
}

const iconSlugs = {
  activity: "activity", gauge: "gauge", chart: "chart-no-axes-combined", scroll: "scroll-text",
  logs: "logs", file: "file-text", bot: "bot", sparkles: "sparkles", wand: "wand-sparkles",
  house: "house", castle: "castle", trees: "trees", users: "users-round", contact: "contact-round",
  "user-settings": "user-round-cog", plug: "plug", cable: "cable", network: "network",
  library: "library-big", boxes: "boxes", brain: "brain-circuit", utensils: "utensils",
  "cooking-pot": "cooking-pot", wheat: "wheat", wrench: "wrench", shield: "shield-check",
  key: "key-round", settings: "settings", sliders: "sliders-horizontal", panels: "panels-top-left",
  cuboid: "cuboid", box: "box", blocks: "blocks", message: "message-circle",
  messages: "messages-square", send: "send", qr: "qr-code", scan: "scan-line", phone: "smartphone",
  profile: "circle-user-round"
} satisfies Record<CatalogIconName, string>

const lucide = (id: CatalogIconName, label: string): IconChoice => ({
  id,
  label,
  url: `https://lucide.dev/icons/${iconSlugs[id]}`
})

export const iconCatalog = [
  { id: "monitor", choices: [lucide("activity", "Activity"), lucide("gauge", "Gauge"), lucide("chart", "Chart")] },
  { id: "logs", choices: [lucide("scroll", "Scroll"), lucide("logs", "Logs"), lucide("file", "File")] },
  { id: "elfies", choices: [lucide("bot", "Bot"), lucide("sparkles", "Sparkles"), lucide("wand", "Wand")] },
  { id: "nest", choices: [lucide("house", "House"), lucide("castle", "Castle"), lucide("trees", "Trees")] },
  { id: "users", choices: [lucide("users", "Users"), lucide("contact", "Contact"), lucide("user-settings", "User settings")] },
  { id: "providers", choices: [lucide("plug", "Plug"), lucide("cable", "Cable"), lucide("network", "Network")] },
  { id: "models", choices: [lucide("library", "Library"), lucide("boxes", "Boxes"), lucide("brain", "Brain")] },
  { id: "foods", choices: [lucide("utensils", "Utensils"), lucide("cooking-pot", "Cooking pot"), lucide("wheat", "Wheat")] },
  { id: "tools", choices: [lucide("wrench", "Wrench"), lucide("shield", "Shield"), lucide("key", "Key")] },
  { id: "system", choices: [lucide("settings", "Settings"), lucide("sliders", "Sliders"), lucide("panels", "Panels")] },
  { id: "godot", choices: [lucide("cuboid", "Cuboid"), lucide("box", "Box"), lucide("blocks", "Blocks")] },
  { id: "chat", choices: [lucide("message", "Message"), lucide("messages", "Messages"), lucide("send", "Send")] },
  { id: "mobile", choices: [lucide("qr", "QR"), lucide("scan", "Scan"), lucide("phone", "Phone")] },
  { id: "profile", choices: [lucide("profile", "Profile"), lucide("user-settings", "User settings"), lucide("settings", "Settings")] }
] satisfies readonly IconCatalogGroup[]
