export const common = {
  actions: {
    cancel: "取消",
    close: "关闭",
    confirm: "确认",
    processing: "处理中…",
  },
  aria: {
    closeDialog: "关闭{{title}}",
    decrease: "减少{{label}}",
    increase: "增加{{label}}",
    notifications: "通知",
  },
  app: {
    welcome: "欢迎使用 {{productName}}",
  },
  language: {
    label: "语言",
  },
  mobileAccess: {
    brand: "手机访问",
    close: "关闭手机访问二维码",
    loading: "正在查找本机局域网地址…",
    localAddress: "本机地址",
    qrAlt: "访问 {{url}} 的二维码",
    qrError: "二维码生成失败",
    title: "用手机打开 ElfieNest",
    unavailable: "当前服务只允许本机访问。请以局域网模式启动后再扫码：",
  },
  status: {
    unknown: "状态未知",
  },
} as const
