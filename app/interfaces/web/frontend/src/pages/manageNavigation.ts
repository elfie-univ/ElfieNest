import type { IconName } from "../components/Icon"

export const MANAGE_NAV_ITEMS = [
  { id: "monitor", icon: "activity" },
  { id: "users", icon: "users" },
  { id: "elfies", icon: "cat" },
  { id: "nest", icon: "house" },
  { id: "providers", icon: "plug-zap" },
  { id: "foods", icon: "utensils" },
  { id: "tools", icon: "wrench" },
  { id: "system", icon: "settings" },
] as const satisfies readonly { readonly id: string; readonly icon: IconName }[]

export type ManageTab = (typeof MANAGE_NAV_ITEMS)[number]["id"]
type ManageNavItem = (typeof MANAGE_NAV_ITEMS)[number]
export type ManageNavGroupId = "operations" | "business" | "models" | "system"
type ManageNavGroup = { readonly id: ManageNavGroupId; readonly items: readonly ManageNavItem[] }

export const MANAGE_NAV_GROUPS: readonly ManageNavGroup[] = [
  {
    id: "operations",
    items: [
      MANAGE_NAV_ITEMS[0],
    ],
  },
  {
    id: "business",
    items: [
      MANAGE_NAV_ITEMS[1], MANAGE_NAV_ITEMS[2], MANAGE_NAV_ITEMS[3],
    ],
  },
  {
    id: "models",
    items: [
      MANAGE_NAV_ITEMS[4], MANAGE_NAV_ITEMS[5],
    ],
  },
  {
    id: "system",
    items: [
      MANAGE_NAV_ITEMS[6], MANAGE_NAV_ITEMS[7],
    ],
  },
]

export function isManageTab(value: string | null): value is ManageTab {
  return MANAGE_NAV_ITEMS.some((item) => item.id === value)
}

export function manageNavItem(tab: ManageTab) {
  return MANAGE_NAV_ITEMS.find((item) => item.id === tab)
}
