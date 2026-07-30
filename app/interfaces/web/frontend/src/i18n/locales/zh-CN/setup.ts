export const setup = {
  errors: {
    bedCount: "床位数必须在 4 到 32 之间。",
    complete: "初始化未能完成。",
    install: "安装未能完成。",
    load: "初始化状态加载失败。",
    passwordMismatch: "两次输入的密码不一致",
    pull: "模型下载未能完成。",
    save: "初始化设置未能保存。",
  },
  finish: {
    action: "进入管理台",
    callout: "管理员、离线保障、精灵巢与模型选择均已记录。你可以随时在管理台继续调整。",
  },
  model: {
    actions: {
      pull: "下载并验证模型",
      save: "验证并保存模型",
      skip: "稍后配置",
    },
    callout: "只会保存固定 Ollama endpoint 中已验证存在的模型；不会把未下载模型伪装成可用。",
    confirmPull: "我同意下载该模型；下载量与耗时取决于模型和网络。",
    fields: {
      reference: "模型（provider_id/model_id）",
    },
    noRecommendation: "当前内存不足 4 GiB 或无法确定，暂不默认推荐本地模型。",
    recommended: "检测到约 {{memory}} GiB 内存，建议先使用 {{model}}。",
    running: "正在下载并验证模型 · {{progress}}%",
    runningHint: "刷新后会继续显示进度。",
  },
  nest: {
    action: "保存房间设置",
    callout: "精灵巢至少保留 4 个床位，最多 32 个；不能设为 1。",
    fields: {
      bedCount: "床位数",
    },
  },
  ollama: {
    actions: {
      bind: "绑定已有 Ollama",
      install: "下载安装官方 Ollama",
      skip: "暂时跳过",
    },
    callout: "Ollama 能在断网或云端不可用时维持精灵的基本模型能力，避免服务完全失去响应。已有公共 Ollama 时，可以固定绑定它；系统不会在之后擅自切换 endpoint。",
    confirmInstall: "我同意从 Ollama 官方站下载并运行适用于本机的安装程序。",
    fields: {
      endpoint: "已有 Ollama endpoint",
    },
    running: "正在安装 Ollama · {{progress}}%",
    runningHint: "请不要关闭此页面；刷新后会继续显示进度。",
  },
  owner: {
    action: "创建管理员账号",
    fields: {
      confirmPassword: "确认密码",
      displayName: "显示名称",
      password: "密码",
      username: "管理员账号",
    },
    submitting: "正在创建…",
  },
  progress: {
    stepCount: "第 {{current}} 步，共 {{total}} 步",
  },
  rail: {
    brand: "初始化向导",
    current: "进行中",
    description: "用五个清晰步骤，把精灵巢准备好。进度会自动保留。",
    footnote: "Ollama 与本地模型均不包含在应用包内；只有你确认后才会调用官方安装或下载流程。",
    pending: "等待此步骤",
    productLabel: "首次家庭设置",
    saved: "已保存",
    stepsLabel: "初始化步骤",
  },
  steps: {
    owner: {
      description: "创建唯一的管理员账号，之后每一步都可安全继续。",
      label: "创建管理员账号",
      title: "先把家安好。",
    },
    ollama: {
      description: "Ollama 是可选的本地模型服务；它能在网络或云端不可用时维持基本能力。",
      label: "离线保障（可选）",
      title: "为离线时刻留一盏灯。",
    },
    nest: {
      description: "房间结构固定，只需要确认初始床位数量。",
      label: "精灵巢床位",
      title: "安排精灵巢。",
    },
    model: {
      description: "只会保存已验证的模型；没有 Ollama 也可以先跳过。",
      label: "模型与粮食",
      title: "选择模型与粮食。",
    },
    finish: {
      description: "确认这些基础设置后，进入 ElfieNest 管理台。",
      label: "确认完成",
      title: "准备完成。",
    },
  },
} as const
