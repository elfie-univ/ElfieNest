export const shellPages = {
  chat: {
    description: "选择一只精灵后开始同源聊天。",
    heading: "与精灵聊天",
    navigation: [
      { href: "/manage", label: "管理" },
      { href: "/login", label: "退出登录" }
    ]
  },
  login: {
    description: "使用你的 ElfieNest 账号继续。",
    heading: "登录 ElfieNest",
    navigation: []
  },
  manage: {
    description: "查看巢与精灵的管理入口。",
    heading: "管理 ElfieNest",
    navigation: [
      { href: "/chat", label: "聊天" },
      { href: "/login", label: "退出登录" }
    ]
  }
} as const

export type ShellPage = keyof typeof shellPages
