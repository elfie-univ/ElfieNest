export const auth = {
  errors: {
    login: "登录失败，请重试。",
  },
  login: {
    action: "登录",
    fields: {
      account: "账号",
      password: "密码",
    },
    submitting: "正在登录…",
  },
} as const
