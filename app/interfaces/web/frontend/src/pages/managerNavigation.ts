import type { IconName } from "../components/Icon"

export const MANAGER_NAV_ITEMS = [
  { id: "monitor", label: "状态监控", icon: "activity" },
  { id: "users", label: "用户管理", icon: "users" },
  { id: "elfies", label: "精灵管理", icon: "cat" },
  { id: "nest", label: "精灵巢管理", icon: "house" },
  { id: "providers", label: "模型订阅", icon: "plug-zap" },
  { id: "foods", label: "粮食策略", icon: "utensils" },
  { id: "tools", label: "工具与权限", icon: "wrench" },
  { id: "system", label: "系统设置", icon: "settings" },
] as const satisfies readonly { readonly id: string; readonly label: string; readonly icon: IconName }[]

export type ManagerTab = (typeof MANAGER_NAV_ITEMS)[number]["id"]
type ManagerNavItem = (typeof MANAGER_NAV_ITEMS)[number]
type ManagerNavGroup = { readonly label: string; readonly items: readonly ManagerNavItem[] }

export const MANAGER_NAV_GROUPS: readonly ManagerNavGroup[] = [
  {
    label: "运行维护",
    items: [
      MANAGER_NAV_ITEMS[0],
    ],
  },
  {
    label: "业务管理",
    items: [
      MANAGER_NAV_ITEMS[1], MANAGER_NAV_ITEMS[2], MANAGER_NAV_ITEMS[3],
    ],
  },
  {
    label: "模型订阅",
    items: [
      MANAGER_NAV_ITEMS[4], MANAGER_NAV_ITEMS[5],
    ],
  },
  {
    label: "系统配置",
    items: [
      MANAGER_NAV_ITEMS[6], MANAGER_NAV_ITEMS[7],
    ],
  },
]

export function isManagerTab(value: string | null): value is ManagerTab {
  return MANAGER_NAV_ITEMS.some((item) => item.id === value)
}

export function managerNavItem(tab: ManagerTab) {
  return MANAGER_NAV_ITEMS.find((item) => item.id === tab)
}
