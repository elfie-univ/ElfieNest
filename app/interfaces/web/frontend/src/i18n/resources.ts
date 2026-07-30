import { account as enUSAccount } from "./locales/en-US/account"
import { auth as enUSAuth } from "./locales/en-US/auth"
import { chat as enUSChat } from "./locales/en-US/chat"
import { common as enUSCommon } from "./locales/en-US/common"
import { manage as enUSManage } from "./locales/en-US/manage"
import { monitor as enUSMonitor } from "./locales/en-US/monitor"
import { setup as enUSSetup } from "./locales/en-US/setup"
import { account as zhCNAccount } from "./locales/zh-CN/account"
import { auth as zhCNAuth } from "./locales/zh-CN/auth"
import { chat as zhCNChat } from "./locales/zh-CN/chat"
import { common as zhCNCommon } from "./locales/zh-CN/common"
import { manage as zhCNManage } from "./locales/zh-CN/manage"
import { monitor as zhCNMonitor } from "./locales/zh-CN/monitor"
import { setup as zhCNSetup } from "./locales/zh-CN/setup"

export const supportedLngs = ["zh-CN", "en-US"] as const
export const namespaces = [
  "common",
  "auth",
  "setup",
  "account",
  "chat",
  "manage",
  "monitor",
] as const
export const defaultNS = "common" as const

type TranslationShape<Source> = Source extends string
  ? string
  : Source extends Readonly<Record<string, unknown>>
    ? { readonly [Key in keyof Source]: TranslationShape<Source[Key]> }
    : never

const zhCNResources = {
  common: zhCNCommon,
  auth: zhCNAuth,
  setup: zhCNSetup,
  account: zhCNAccount,
  chat: zhCNChat,
  manage: zhCNManage,
  monitor: zhCNMonitor,
} as const

const enUSResources = {
  common: enUSCommon,
  auth: enUSAuth,
  setup: enUSSetup,
  account: enUSAccount,
  chat: enUSChat,
  manage: enUSManage,
  monitor: enUSMonitor,
} as const satisfies TranslationShape<typeof zhCNResources>

export const resources = {
  "zh-CN": zhCNResources,
  "en-US": enUSResources,
} as const
