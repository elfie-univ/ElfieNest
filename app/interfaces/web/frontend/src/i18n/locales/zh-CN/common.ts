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
    unavailable: "手机访问暂不可用，当前只能在这台电脑上使用。请确认电脑和手机连接在同一局域网后重试。",
  },
  status: {
    unknown: "状态未知",
  },
} as const
