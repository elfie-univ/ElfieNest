import { useEffect, useState, type FormEvent } from "react"

import {
  ApiError,
  currentUser,
  setup,
  setupBindExistingOllama,
  setupComplete,
  setupConfiguredModel,
  setupInstallOfficialOllama,
  setupModelRecommendation,
  setupNest,
  setupPullModel,
  setupSkipModel,
  setupSkipOllama,
  setupStatus,
  type SetupModelRecommendation,
  type SetupStatus,
} from "../api/client"
import { Notice } from "../components/Notice"

const SETUP_STEPS = [
  "创建管理员账号",
  "离线保障（可选）",
  "精灵巢床位",
  "模型与粮食",
  "确认完成",
] as const

const DEFAULT_SETUP_HEADING: readonly [string, string] = [
  "先把家安好。",
  "创建唯一的管理员账号，之后每一步都可安全继续。",
]

const SETUP_HEADINGS: Readonly<Record<number, readonly [string, string]>> = {
  1: DEFAULT_SETUP_HEADING,
  2: ["为离线时刻留一盏灯。", "Ollama 是可选的本地模型服务；它能在网络或云端不可用时维持基本能力。"],
  3: ["安排精灵巢。", "房间结构固定，只需要确认初始床位数量。"],
  4: ["选择模型与粮食。", "只会保存已验证的模型；没有 Ollama 也可以先跳过。"],
  5: ["准备完成。", "确认这些基础设置后，进入 ElfieNest 管理台。"],
}

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof ApiError ? reason.message : fallback
}

export function SetupPage() {
  const [username, setUsername] = useState("")
  const [displayName, setDisplayName] = useState("")
  const [password, setPassword] = useState("")
  const [passwordConfirmation, setPasswordConfirmation] = useState("")
  const [bedCount, setBedCount] = useState(4)
  const [ollamaEndpoint, setOllamaEndpoint] = useState("http://127.0.0.1:11434")
  const [ollamaInstallConfirmed, setOllamaInstallConfirmed] = useState(false)
  const [progress, setProgress] = useState<SetupStatus | null>(null)
  const [modelRecommendation, setModelRecommendation] = useState<SetupModelRecommendation | null>(null)
  const [modelReference, setModelReference] = useState("")
  const [modelPullConfirmed, setModelPullConfirmed] = useState(false)
  const [csrfToken, setCsrfToken] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    const load = (): void => {
      void Promise.all([setupStatus(), currentUser().catch(() => null)])
        .then(([status, user]) => {
          setProgress(status)
          if (user?.csrf_token) setCsrfToken(user.csrf_token)
        })
        .catch(() => setError("无法读取初始化进度"))
    }
    load()
    const timer = window.setInterval(load, 2000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    if (progress?.current_step !== 4) return
    void setupModelRecommendation().then(setModelRecommendation).catch(() => setModelRecommendation(null))
  }, [progress?.current_step])

  const submitOwner = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    if (password !== passwordConfirmation) {
      setError("两次输入的密码不一致")
      return
    }
    setSaving(true)
    setError(null)
    try {
      const result = await setup(username.trim(), password, displayName.trim())
      setCsrfToken(result.csrf_token)
      setProgress(await setupStatus())
    } catch (reason: unknown) {
      setError(errorMessage(reason, "初始化未完成"))
    } finally {
      setSaving(false)
    }
  }

  const completeStep = async (action: () => Promise<SetupStatus>): Promise<void> => {
    setSaving(true)
    setError(null)
    try {
      const status = await action()
      setProgress(status)
      if (status.complete) window.location.assign("/manage")
    } catch (reason: unknown) {
      setError(errorMessage(reason, "此步骤尚未完成"))
    } finally {
      setSaving(false)
    }
  }

  const currentStep = progress?.current_step ?? 1
  const [heading, description] = SETUP_HEADINGS[currentStep] ?? DEFAULT_SETUP_HEADING
  const steps = progress?.steps ?? SETUP_STEPS.map((name, index) => ({
    name,
    number: index + 1,
    status: index === 0 ? "current" : "pending",
  }))

  return <main className="setup-page">
    <aside className="setup-rail">
      <div className="setup-brand">
        <span aria-hidden="true" className="setup-brand__mark">EN</span>
        <span><strong>ELFIE NEST</strong><small>FIRST HOME SETUP</small></span>
      </div>
      <div className="setup-rail__intro">
        <p className="brand">初始化向导</p>
        <p>用五个清晰步骤，把精灵巢准备好。进度会自动保留。</p>
      </div>
      <ol aria-label="初始化步骤" className="setup-steps">
        {steps.map((step) => {
          const completed = step.status === "completed"
          const current = step.number === currentStep
          const className = completed
            ? "setup-step setup-step--completed"
            : current ? "setup-step setup-step--current" : "setup-step"
          return <li className={className} key={step.number}>
            <span aria-hidden="true" className="setup-step__number">{completed ? "✓" : step.number}</span>
            <span><strong>{step.name}</strong><small>{completed ? "已保存" : current ? "进行中" : "等待此步骤"}</small></span>
          </li>
        })}
      </ol>
      <p className="setup-rail__footnote">Ollama 与本地模型均不包含在应用包内；只有你确认后才会调用官方安装或下载流程。</p>
    </aside>
    <section className="setup-main">
      <section aria-labelledby="setup-title" className="panel setup-card">
        <header className="setup-card__header">
          <p className="brand">步骤 {currentStep} / 5</p>
          <h1 id="setup-title">{heading}</h1>
          <p>{description}</p>
        </header>
        <div className="setup-card__content">
          {currentStep === 1 && <form className="setup-form" onSubmit={(event) => { void submitOwner(event) }}>
            <label>管理员账号<input autoComplete="username" minLength={3} onChange={(event) => setUsername(event.target.value)} required value={username} /></label>
            <label>显示名称<input autoComplete="name" onChange={(event) => setDisplayName(event.target.value)} required value={displayName} /></label>
            <label>密码<input autoComplete="new-password" minLength={6} onChange={(event) => setPassword(event.target.value)} required type="password" value={password} /></label>
            <label>确认密码<input autoComplete="new-password" minLength={6} onChange={(event) => setPasswordConfirmation(event.target.value)} required type="password" value={passwordConfirmation} /></label>
            <div className="setup-actions"><button className="button" disabled={saving} type="submit">{saving ? "正在创建…" : "创建管理员账号"}</button></div>
          </form>}
          {currentStep === 2 && <section className="setup-form">
            <p className="setup-callout">Ollama 能在断网或云端不可用时维持精灵的基本模型能力，避免服务完全失去响应。已有公共 Ollama 时，可以固定绑定它；系统不会在之后擅自切换 endpoint。</p>
            <label>已有 Ollama endpoint<input onChange={(event) => setOllamaEndpoint(event.target.value)} type="url" value={ollamaEndpoint} /></label>
            {progress?.task?.state === "running" ? <p className="setup-task">正在安装 Ollama · {progress.task.progress}%<span>请不要关闭此页面；刷新后会继续显示进度。</span></p> : <>
              <label className="setup-check"><input checked={ollamaInstallConfirmed} onChange={(event) => setOllamaInstallConfirmed(event.target.checked)} type="checkbox" />我同意从 Ollama 官方站下载并运行适用于本机的安装程序。</label>
              <div className="setup-actions"><button className="button" disabled={saving || !csrfToken || !ollamaInstallConfirmed} onClick={() => { void completeStep(() => setupInstallOfficialOllama(csrfToken)) }} type="button">下载安装官方 Ollama</button><button className="button button--quiet" disabled={saving || !csrfToken} onClick={() => { void completeStep(() => setupBindExistingOllama(ollamaEndpoint.trim(), csrfToken)) }} type="button">绑定已有 Ollama</button><button className="button button--quiet" disabled={saving || !csrfToken} onClick={() => { void completeStep(() => setupSkipOllama(csrfToken)) }} type="button">暂时跳过</button></div>
            </>}
          </section>}
          {currentStep === 3 && <section className="setup-form">
            <p className="setup-callout">精灵巢至少保留 4 个床位，最多 32 个；不能设为 1。</p>
            <label>床位数<input max={32} min={4} onChange={(event) => setBedCount(Number(event.target.value))} type="number" value={bedCount} /></label>
            <div className="setup-actions"><button className="button" disabled={saving || !csrfToken} onClick={() => { void completeStep(() => setupNest(bedCount, csrfToken)) }} type="button">保存房间设置</button></div>
          </section>}
          {currentStep === 4 && <section className="setup-form">
            <p className="setup-callout">只会保存固定 Ollama endpoint 中已验证存在的模型；不会把未下载模型伪装成可用。</p>
            {progress?.task?.state === "running" ? <p className="setup-task">正在下载并验证模型 · {progress.task.progress}%<span>刷新后会继续显示进度。</span></p> : <>
              {modelRecommendation?.recommended_model ? <p className="setup-hint">检测到约 {modelRecommendation.memory_gb} GiB 内存，建议先使用 {modelRecommendation.recommended_model}。</p> : <p className="setup-hint">当前内存不足 4 GiB 或无法确定，暂不默认推荐本地模型。</p>}
              <label>模型（provider_id/model_id）<input onChange={(event) => setModelReference(event.target.value)} placeholder="ollama/qwen2.5:0.5b" value={modelReference} /></label>
              <label className="setup-check"><input checked={modelPullConfirmed} onChange={(event) => setModelPullConfirmed(event.target.checked)} type="checkbox" />我同意下载该模型；下载量与耗时取决于模型和网络。</label>
              <div className="setup-actions"><button className="button" disabled={saving || !csrfToken || !modelReference.trim()} onClick={() => { void completeStep(() => setupConfiguredModel(modelReference.trim(), csrfToken)) }} type="button">验证并保存模型</button><button className="button button--quiet" disabled={saving || !csrfToken || !modelReference.trim() || !modelPullConfirmed} onClick={() => { void completeStep(() => setupPullModel(modelReference.trim(), csrfToken)) }} type="button">下载并验证模型</button><button className="button button--quiet" disabled={saving || !csrfToken} onClick={() => { void completeStep(() => setupSkipModel(csrfToken)) }} type="button">稍后配置</button></div>
            </>}
          </section>}
          {currentStep === 5 && <section className="setup-form">
            <p className="setup-callout">管理员、离线保障、精灵巢与模型选择均已记录。你可以随时在管理台继续调整。</p>
            <div className="setup-actions"><button className="button" disabled={saving || !csrfToken} onClick={() => { void completeStep(() => setupComplete(csrfToken)) }} type="button">进入管理台</button></div>
          </section>}
          {error && <Notice kind="error" message={error} />}
        </div>
      </section>
    </section>
  </main>
}
