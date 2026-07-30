export const auth = {
  errors: {
    login: "登录失败，请重试。",
  },
  login: {
    action: "进入 ElfieNest",
    brand: "ELFIENEST · 家庭精灵巢",
    description: "登录后进入属于你的聊天与管理空间。",
    fields: {
      account: "账号",
      password: "密码",
    },
    submitting: "正在登录…",
    title: "回来吧，精灵正在等你。",
  },
  session: {
    signedInAs: "已登录为{{accountName}}",
  },
} as const
