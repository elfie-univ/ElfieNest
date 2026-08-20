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
    connectSameWifi: "第一步　手机连接同一无线网",
    connectWifi: "第一步　手机连接无线网",
    loading: "正在查找本机局域网地址…",
    localAddress: "本机地址",
    qrAlt: "访问 {{url}} 的二维码",
    qrError: "二维码生成失败",
    scanQr: "第二步　用手机扫描二维码",
    title: "用手机打开 ElfieNest",
    unavailable: "手机访问暂不可用，当前只能在这台电脑上使用。请确认电脑和手机连接在同一局域网后重试。",
    wifiNameUnavailable: "当前系统无法提供无线网名称，但不影响扫码。",
    wifiPermissionDenied: "没有获得读取无线网名称的权限。只要手机和电脑在同一局域网，仍可继续扫码。",
    wifiPermissionRequesting: "正在请求 macOS 权限以显示当前无线网名称；二维码仍可正常使用。",
    openLocationSettings: "打开定位服务设置",
  },
  status: {
    unknown: "状态未知",
  },
} as const
