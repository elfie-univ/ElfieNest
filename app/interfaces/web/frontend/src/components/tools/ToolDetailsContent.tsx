import type { LocalFileToolConfig, ToolKey, ToolPermissionAction, ValidationSuite } from "../../api/owner-tools"
import type { LocalFileDraftUpdate, PermissionMode, WebSearchDraft, WebSearchDraftUpdate } from "./tool-model"
import { permissionActionForTool } from "./tool-model"
import { LocalFileToolDetails } from "./LocalFileToolDetails"
import { ToolPermissionDetails } from "./ToolPermissionDetails"
import { WebSearchToolDetails } from "./WebSearchToolDetails"

type ToolDetailsContentProps = {
  readonly dirtyPermission: boolean
  readonly dirtyTool: boolean
  readonly localFile: LocalFileToolConfig
  readonly permissionError: string | null
  readonly permissionMode: PermissionMode
  readonly savingPermission: boolean
  readonly savingTool: boolean
  readonly toolError: string | null
  readonly toolKey: ToolKey
  readonly verification: ValidationSuite | null
  readonly verifying: boolean
  readonly webSearch: WebSearchDraft
  readonly onCancelPermission: (action: ToolPermissionAction) => void
  readonly onCancelTool: (toolKey: ToolKey) => void
  readonly onChangeLocalFile: (update: LocalFileDraftUpdate) => void
  readonly onChangePermission: (mode: "allow" | "deny") => void
  readonly onChangeWebSearch: (update: WebSearchDraftUpdate) => void
  readonly onSavePermission: (action: ToolPermissionAction) => void
  readonly onSaveTool: (toolKey: ToolKey) => void
  readonly onVerifyTool: (toolKey: ToolKey) => void
}

export function ToolDetailsContent({
  dirtyPermission,
  dirtyTool,
  localFile,
  permissionError,
  permissionMode,
  savingPermission,
  savingTool,
  toolError,
  toolKey,
  verification,
  verifying,
  webSearch,
  onCancelPermission,
  onCancelTool,
  onChangeLocalFile,
  onChangePermission,
  onChangeWebSearch,
  onSavePermission,
  onSaveTool,
  onVerifyTool,
}: ToolDetailsContentProps) {
  const action = permissionActionForTool(toolKey)
  const permission = <ToolPermissionDetails
    action={action}
    dirty={dirtyPermission}
    error={permissionError}
    mode={permissionMode}
    onChange={onChangePermission}
    onSave={() => onSavePermission(action)}
    saving={savingPermission}
  />

  switch (toolKey) {
    case "web_search":
      return <>
        <WebSearchToolDetails
          dirty={dirtyTool}
          draft={webSearch}
          error={toolError}
          onCancel={() => onCancelTool(toolKey)}
          onChange={onChangeWebSearch}
          onSave={() => onSaveTool(toolKey)}
          onVerify={() => onVerifyTool(toolKey)}
          saving={savingTool}
          verification={verification}
          verifying={verifying}
        />
        {permission}
      </>
    case "local_file":
      return <>
        <LocalFileToolDetails
          dirty={dirtyTool}
          draft={localFile}
          error={toolError}
          onCancel={() => onCancelTool(toolKey)}
          onChange={onChangeLocalFile}
          onSave={() => onSaveTool(toolKey)}
          onVerify={() => onVerifyTool(toolKey)}
          saving={savingTool}
          verification={verification}
          verifying={verifying}
        />
        {permission}
      </>
  }
}
