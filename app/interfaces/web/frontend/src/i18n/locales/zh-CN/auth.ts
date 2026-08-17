export const auth = {
  errors: {
    login: "登录失败，请重试。",
    register: "注册失败，请重试。",
  },
  login: {
    action: "登录",
    registerAction: "注册并进入",
    registerSubmitting: "正在注册并登录…",
    switchToLogin: "已有账号？返回登录",
    switchToRegister: "没有账号？立即注册",
    fields: {
      account: "账号",
      confirmPassword: "确认密码",
      displayName: "显示名称",
      password: "密码",
    },
    passwordMismatch: "两次输入的密码不一致。",
    submitting: "正在登录…",
  },
} as const
