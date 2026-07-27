import type { IconName } from "../components/Icon"

export const MANAGE_NAV_ITEMS = [
  { id: "monitor", label: "状态监控", icon: "activity" },
  { id: "users", label: "用户管理", icon: "users" },
  { id: "elfies", label: "精灵管理", icon: "cat" },
  { id: "nest", label: "精灵巢管理", icon: "house" },
  { id: "providers", label: "模型订阅", icon: "plug-zap" },
  { id: "foods", label: "粮食策略", icon: "utensils" },
  { id: "tools", label: "工具与权限", icon: "wrench" },
  { id: "system", label: "系统设置", icon: "settings" },
] as const satisfies readonly { readonly id: string; readonly label: string; readonly icon: IconName }[]

export type ManageTab = (typeof MANAGE_NAV_ITEMS)[number]["id"]
type ManageNavItem = (typeof MANAGE_NAV_ITEMS)[number]
type ManageNavGroup = { readonly label: string; readonly items: readonly ManageNavItem[] }

export const MANAGE_NAV_GROUPS: readonly ManageNavGroup[] = [
  {
    label: "运行维护",
    items: [
      MANAGE_NAV_ITEMS[0],
    ],
  },
  {
    label: "业务管理",
    items: [
      MANAGE_NAV_ITEMS[1], MANAGE_NAV_ITEMS[2], MANAGE_NAV_ITEMS[3],
    ],
  },
  {
    label: "模型订阅",
    items: [
      MANAGE_NAV_ITEMS[4], MANAGE_NAV_ITEMS[5],
    ],
  },
  {
    label: "系统配置",
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
