export const auth = {
  errors: {
    login: "登录失败，请重试。",
  },
  login: {
    action: "登录",
    brand: "ELFIENEST",
    fields: {
      account: "账号",
      password: "密码",
    },
    submitting: "正在登录…",
    title: "登录",
  },
  session: {
    signedInAs: "已登录为{{accountName}}",
  },
} as const
