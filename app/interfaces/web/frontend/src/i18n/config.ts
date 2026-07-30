import { createInstance, type i18n, type InitOptions } from "i18next"
import { initReactI18next } from "react-i18next"

import { defaultNS, namespaces, resources, supportedLngs } from "./resources"

export const i18nOptions = {
  resources,
  lng: "zh-CN",
  supportedLngs,
  fallbackLng: "zh-CN",
  load: "currentOnly",
  ns: namespaces,
  defaultNS,
  returnNull: false,
  initAsync: false,
  interpolation: {
    escapeValue: false,
  },
  react: {
    useSuspense: false,
  },
} as const satisfies InitOptions

export function createI18n(): i18n {
  const instance = createInstance()
  const instanceOptions = {
    ...i18nOptions,
    supportedLngs: [...supportedLngs],
    ns: [...namespaces],
    interpolation: { ...i18nOptions.interpolation },
    react: { ...i18nOptions.react },
  } satisfies InitOptions
  instance.use(initReactI18next)
  void instance.init(instanceOptions)
  return instance
}
