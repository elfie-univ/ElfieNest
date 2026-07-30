import "i18next"

import type { defaultNS, resources } from "./resources"

declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: typeof defaultNS
    returnNull: false
    strictKeyChecks: true
    resources: (typeof resources)["zh-CN"]
  }
}
