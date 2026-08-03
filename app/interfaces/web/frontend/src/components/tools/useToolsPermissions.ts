import { useEffect, useState } from "react"

import {
  ownerRuntimeAudit,
  ownerRuntimePolicy,
  ownerRuntimeTools,
  updateOwnerTool,
  updateToolPermission,
  verifyOwnerTool,
  type EditablePermissionMode,
  type LocalFileToolUpdate,
  type RuntimeAudit,
  type RuntimePolicy,
  type ToolKey,
  type ToolPermissionAction,
  type ToolConfigMap,
  type ValidationSuite,
  type WebSearchToolUpdate,
} from "../../api/owner-tools"
import { describeApiError, type LocalizedErrorState } from "../../i18n/errors"
import {
  createPermissionDrafts,
  createToolDrafts,
  type LocalFileDraftUpdate,
  type PermissionDrafts,
  type ToolDrafts,
  type WebSearchDraftUpdate,
} from "./tool-model"

type ToolErrorMap = Readonly<Record<ToolKey, LocalizedErrorState>>
type PermissionErrorMap = Readonly<Record<ToolPermissionAction, LocalizedErrorState>>
type VerificationMap = Readonly<Record<ToolKey, ValidationSuite | null>>

export type ToolsPermissionsState = Readonly<{
  readonly audit: RuntimeAudit | null
  readonly auditError: LocalizedErrorState
  readonly auditLoading: boolean
  readonly dirtyPermissions: readonly ToolPermissionAction[]
  readonly dirtyTools: readonly ToolKey[]
  readonly drafts: ToolDrafts | null
  readonly error: LocalizedErrorState
  readonly expanded: readonly ToolKey[]
  readonly permissionDrafts: PermissionDrafts | null
  readonly permissionErrors: PermissionErrorMap
  readonly policy: RuntimePolicy | null
  readonly savingPermission: ToolPermissionAction | null
  readonly savingTool: ToolKey | null
  readonly toolErrors: ToolErrorMap
  readonly verification: VerificationMap
  readonly verifying: ToolKey | null
}>

const emptyToolErrors: ToolErrorMap = { web_search: null, local_file: null }
const emptyPermissionErrors: PermissionErrorMap = { WEB_SEARCH: null, READ: null }
const emptyVerification: VerificationMap = { web_search: null, local_file: null }

function removeTool(current: readonly ToolKey[], key: ToolKey): readonly ToolKey[] {
  return current.filter((item) => item !== key)
}

function removePermission(current: readonly ToolPermissionAction[], action: ToolPermissionAction): readonly ToolPermissionAction[] {
  return current.filter((item) => item !== action)
}

function isEditablePermissionMode(mode: PermissionDrafts["WEB_SEARCH"]): mode is EditablePermissionMode {
  return mode === "allow" || mode === "deny"
}

export function useToolsPermissions(csrfToken: string): ToolsPermissionsState & {
  readonly cancelPermission: (action: ToolPermissionAction) => void
  readonly cancelTool: (toolKey: ToolKey) => void
  readonly changeLocalFile: (update: LocalFileDraftUpdate) => void
  readonly changePermission: (action: ToolPermissionAction, mode: EditablePermissionMode) => void
  readonly changeWebSearch: (update: WebSearchDraftUpdate) => void
  readonly savePermission: (action: ToolPermissionAction) => Promise<void>
  readonly saveTool: (toolKey: ToolKey) => Promise<void>
  readonly toggleExpanded: (toolKey: ToolKey) => void
  readonly toggleTool: (toolKey: ToolKey, enabled: boolean) => void
  readonly verifyTool: (toolKey: ToolKey) => Promise<void>
} {
  const [configs, setConfigs] = useState<ToolConfigMap | null>(null)
  const [drafts, setDrafts] = useState<ToolDrafts | null>(null)
  const [policy, setPolicy] = useState<RuntimePolicy | null>(null)
  const [permissionDrafts, setPermissionDrafts] = useState<PermissionDrafts | null>(null)
  const [expanded, setExpanded] = useState<readonly ToolKey[]>([])
  const [dirtyTools, setDirtyTools] = useState<readonly ToolKey[]>([])
  const [dirtyPermissions, setDirtyPermissions] = useState<readonly ToolPermissionAction[]>([])
  const [error, setError] = useState<LocalizedErrorState>(null)
  const [toolErrors, setToolErrors] = useState<ToolErrorMap>(emptyToolErrors)
  const [permissionErrors, setPermissionErrors] = useState<PermissionErrorMap>(emptyPermissionErrors)
  const [savingTool, setSavingTool] = useState<ToolKey | null>(null)
  const [savingPermission, setSavingPermission] = useState<ToolPermissionAction | null>(null)
  const [verifying, setVerifying] = useState<ToolKey | null>(null)
  const [verification, setVerification] = useState<VerificationMap>(emptyVerification)
  const [audit, setAudit] = useState<RuntimeAudit | null>(null)
  const [auditError, setAuditError] = useState<LocalizedErrorState>(null)
  const [auditLoading, setAuditLoading] = useState(true)

  useEffect(() => {
    let active = true
    const load = async (): Promise<void> => {
      try {
        const [loadedConfigs, loadedPolicy] = await Promise.all([ownerRuntimeTools(), ownerRuntimePolicy()])
        if (!active) return
        setConfigs(loadedConfigs)
        setDrafts(createToolDrafts(loadedConfigs))
        setPolicy(loadedPolicy)
        setPermissionDrafts(createPermissionDrafts(loadedPolicy))
        setError(null)
        try {
          const loadedAudit = await ownerRuntimeAudit(10)
          if (active) setAudit(loadedAudit)
        } catch (reason: unknown) {
          const failure = reason instanceof Error ? describeApiError(reason, "manage.load") : describeApiError(new Error("Unexpected runtime tools error"), "manage.load")
          if (active) setAuditError(failure)
        } finally {
          if (active) setAuditLoading(false)
        }
      } catch (reason: unknown) {
        if (active) {
          const failure = reason instanceof Error ? describeApiError(reason, "manage.load") : describeApiError(new Error("Unexpected runtime tools error"), "manage.load")
          setError(failure)
          setAuditLoading(false)
        }
      }
    }
    void load()
    return () => { active = false }
  }, [])

  const toggleExpanded = (toolKey: ToolKey): void => {
    setExpanded((current) => current.includes(toolKey)
      ? current.filter((item) => item !== toolKey)
      : [...current, toolKey])
  }

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

  const changePermission = (action: ToolPermissionAction, mode: EditablePermissionMode): void => {
    setPermissionDrafts((current) => current === null ? current : { ...current, [action]: mode })
    setDirtyPermissions((current) => current.includes(action) ? current : [...current, action])
  }

  const cancelPermission = (action: ToolPermissionAction): void => {
    if (policy === null) return
    setPermissionDrafts((current) => current === null ? current : { ...current, [action]: policy.tool_permissions[action].mode })
    setDirtyPermissions((current) => removePermission(current, action))
    setPermissionErrors((current) => ({ ...current, [action]: null }))
  }

  const savePermission = async (action: ToolPermissionAction): Promise<void> => {
    if (permissionDrafts === null || savingPermission !== null) return
    const mode = permissionDrafts[action]
    if (!isEditablePermissionMode(mode)) return
    setSavingPermission(action)
    setPermissionErrors((current) => ({ ...current, [action]: null }))
    try {
      const saved = await updateToolPermission(action, mode, csrfToken)
      setPolicy(saved)
      setPermissionDrafts(createPermissionDrafts(saved))
      setDirtyPermissions((current) => removePermission(current, action))
    } catch (reason: unknown) {
      const failure = reason instanceof Error ? describeApiError(reason, "manage.save") : describeApiError(new Error("Unexpected runtime tools error"), "manage.save")
      setPermissionErrors((current) => ({ ...current, [action]: failure }))
    } finally {
      setSavingPermission(null)
    }
  }

  return {
    audit,
    auditError,
    auditLoading,
    cancelPermission,
    cancelTool,
    changeLocalFile,
    changePermission,
    changeWebSearch,
    dirtyPermissions,
    dirtyTools,
    drafts,
    error,
    expanded,
    permissionDrafts,
    permissionErrors,
    policy,
    savePermission,
    saveTool,
    savingPermission,
    savingTool,
    toolErrors,
    toggleExpanded,
    toggleTool,
    verification,
    verifyTool,
    verifying,
  }
}
