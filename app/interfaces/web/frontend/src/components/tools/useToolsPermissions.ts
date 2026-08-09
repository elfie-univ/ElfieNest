import { useEffect, useState } from "react"

import {
  ownerRuntimeTools,
  updateOwnerTool,
  verifyOwnerTool,
  type LocalFileToolUpdate,
  type ToolKey,
  type ToolConfigMap,
  type ValidationSuite,
  type WebSearchToolUpdate,
} from "../../api/owner-tools"
import { describeApiError, type LocalizedErrorState } from "../../i18n/errors"
import {
  createToolDrafts,
  type LocalFileDraftUpdate,
  type ToolDrafts,
  type WebSearchDraftUpdate,
} from "./tool-model"

type ToolErrorMap = Readonly<Record<ToolKey, LocalizedErrorState>>
type VerificationMap = Readonly<Record<ToolKey, ValidationSuite | null>>

export type ToolsPermissionsState = Readonly<{
  readonly dirtyTools: readonly ToolKey[]
  readonly drafts: ToolDrafts | null
  readonly error: LocalizedErrorState
  readonly savingTool: ToolKey | null
  readonly toolErrors: ToolErrorMap
  readonly verification: VerificationMap
  readonly verifying: ToolKey | null
}>

const emptyToolErrors: ToolErrorMap = { web_search: null, local_file: null }
const emptyVerification: VerificationMap = { web_search: null, local_file: null }

function removeTool(current: readonly ToolKey[], key: ToolKey): readonly ToolKey[] {
  return current.filter((item) => item !== key)
}

export function useToolsPermissions(csrfToken: string): ToolsPermissionsState & {
  readonly cancelTool: (toolKey: ToolKey) => void
  readonly changeLocalFile: (update: LocalFileDraftUpdate) => void
  readonly changeWebSearch: (update: WebSearchDraftUpdate) => void
  readonly saveTool: (toolKey: ToolKey) => Promise<void>
  readonly toggleTool: (toolKey: ToolKey, enabled: boolean) => void
  readonly verifyTool: (toolKey: ToolKey) => Promise<void>
} {
  const [configs, setConfigs] = useState<ToolConfigMap | null>(null)
  const [drafts, setDrafts] = useState<ToolDrafts | null>(null)
  const [dirtyTools, setDirtyTools] = useState<readonly ToolKey[]>([])
  const [error, setError] = useState<LocalizedErrorState>(null)
  const [toolErrors, setToolErrors] = useState<ToolErrorMap>(emptyToolErrors)
  const [savingTool, setSavingTool] = useState<ToolKey | null>(null)
  const [verifying, setVerifying] = useState<ToolKey | null>(null)
  const [verification, setVerification] = useState<VerificationMap>(emptyVerification)

  useEffect(() => {
    let active = true
    const load = async (): Promise<void> => {
      try {
        const loadedConfigs = await ownerRuntimeTools()
        if (!active) return
        setConfigs(loadedConfigs)
        setDrafts(createToolDrafts(loadedConfigs))
        setError(null)
      } catch (reason: unknown) {
        if (active) {
          const failure = reason instanceof Error ? describeApiError(reason, "manage.load") : describeApiError(new Error("Unexpected runtime tools error"), "manage.load")
          setError(failure)
        }
      }
    }
    void load()
    return () => { active = false }
  }, [])

  const toggleTool = (toolKey: ToolKey, enabled: boolean): void => {
    if (toolKey === "web_search") changeWebSearch({ enabled })
    else changeLocalFile({ enabled })
  }

  const changeWebSearch = (update: WebSearchDraftUpdate): void => {
    setDrafts((current) => current === null ? current : { ...current, web_search: { ...current.web_search, ...update } })
    setDirtyTools((current) => current.includes("web_search") ? current : [...current, "web_search"])
  }

  const changeLocalFile = (update: LocalFileDraftUpdate): void => {
    setDrafts((current) => current === null ? current : { ...current, local_file: { ...current.local_file, ...update } })
    setDirtyTools((current) => current.includes("local_file") ? current : [...current, "local_file"])
  }

  const cancelTool = (toolKey: ToolKey): void => {
    if (configs === null) return
    if (toolKey === "web_search") setDrafts((current) => current === null ? current : { ...current, web_search: { ...configs.web_search, api_key: "" } })
    else setDrafts((current) => current === null ? current : { ...current, local_file: configs.local_file })
    setDirtyTools((current) => removeTool(current, toolKey))
    setToolErrors((current) => ({ ...current, [toolKey]: null }))
  }

  const saveTool = async (toolKey: ToolKey): Promise<void> => {
    if (drafts === null || savingTool !== null) return
    setSavingTool(toolKey)
    setToolErrors((current) => ({ ...current, [toolKey]: null }))
    try {
      if (toolKey === "web_search") {
        const draft = drafts.web_search
        let update: WebSearchToolUpdate = {
          enabled: draft.enabled,
          provider: draft.provider,
          api_base: draft.api_base,
          max_results: draft.max_results,
          max_result_bytes: draft.max_result_bytes,
        }
        if (draft.api_key.length > 0) update = { ...update, api_key: draft.api_key }
        const saved = await updateOwnerTool("web_search", update, csrfToken)
        setConfigs((current) => current === null ? current : { ...current, web_search: saved })
        setDrafts((current) => current === null ? current : { ...current, web_search: { ...saved, api_key: "" } })
      } else {
        const draft = drafts.local_file
        const update: LocalFileToolUpdate = { enabled: draft.enabled, max_read_bytes: draft.max_read_bytes }
        const saved = await updateOwnerTool("local_file", update, csrfToken)
        setConfigs((current) => current === null ? current : { ...current, local_file: saved })
        setDrafts((current) => current === null ? current : { ...current, local_file: saved })
      }
      setDirtyTools((current) => removeTool(current, toolKey))
    } catch (reason: unknown) {
      const failure = reason instanceof Error ? describeApiError(reason, "manage.save") : describeApiError(new Error("Unexpected runtime tools error"), "manage.save")
      setToolErrors((current) => ({ ...current, [toolKey]: failure }))
    } finally {
      setSavingTool(null)
    }
  }

  const verifyTool = async (toolKey: ToolKey): Promise<void> => {
    if (drafts === null || dirtyTools.includes(toolKey) || verifying !== null) return
    setVerifying(toolKey)
    setToolErrors((current) => ({ ...current, [toolKey]: null }))
    try {
      const result = await verifyOwnerTool(toolKey, csrfToken)
      setVerification((current) => ({ ...current, [toolKey]: result }))
    } catch (reason: unknown) {
      const failure = reason instanceof Error ? describeApiError(reason, "manage.save") : describeApiError(new Error("Unexpected runtime tools error"), "manage.save")
      setToolErrors((current) => ({ ...current, [toolKey]: failure }))
    } finally {
      setVerifying(null)
    }
  }

  return {
    cancelTool,
    changeLocalFile,
    changeWebSearch,
    dirtyTools,
    drafts,
    error,
    saveTool,
    savingTool,
    toolErrors,
    toggleTool,
    verification,
    verifyTool,
    verifying,
  }
}
