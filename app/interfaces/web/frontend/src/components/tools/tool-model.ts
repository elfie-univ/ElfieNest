import type {
  LocalFileToolConfig,
  ToolConfigMap,
  WebSearchToolConfig,
} from "../../api/owner-tools"

export type WebSearchDraft = Readonly<WebSearchToolConfig & {
  readonly api_key: string
}>
export type WebSearchDraftUpdate = Readonly<Partial<Pick<
  WebSearchDraft,
  "enabled" | "provider" | "api_base" | "api_key" | "max_results" | "max_result_bytes"
>>>
export type LocalFileDraftUpdate = Readonly<Partial<Pick<LocalFileToolConfig, "enabled" | "max_read_bytes">>>
export type ToolDrafts = Readonly<{
  readonly web_search: WebSearchDraft
  readonly local_file: LocalFileToolConfig
}>

export function assertNever(value: never): never {
  throw new Error(`Unsupported tool key: ${String(value)}`)
}

export function createToolDrafts(configs: ToolConfigMap): ToolDrafts {
  return {
    web_search: { ...configs.web_search, api_key: "" },
    local_file: configs.local_file,
  }
}
