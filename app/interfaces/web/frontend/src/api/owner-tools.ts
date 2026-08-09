import { z } from "zod"

import { ownerRead, ownerWrite } from "./http"

export const TOOL_KEYS = ["web_search", "local_file"] as const
export type ToolKey = (typeof TOOL_KEYS)[number]

export const SEARCH_PROVIDERS = ["duckduckgo", "brave", "tavily"] as const
export type SearchProvider = (typeof SEARCH_PROVIDERS)[number]

const SearchProviderSchema = z.enum(SEARCH_PROVIDERS)

const WebSearchToolConfigSchema = z.object({
  enabled: z.boolean(),
  provider: SearchProviderSchema,
  api_base: z.string(),
  max_results: z.number().int().min(1),
  max_result_bytes: z.number().int().positive(),
  timeout_seconds: z.number().positive(),
  max_tool_calls: z.number().int().positive(),
  max_total_result_bytes: z.number().int().positive(),
  has_api_key: z.boolean(),
})

const LocalFileToolConfigSchema = z.object({
  enabled: z.boolean(),
  root: z.string(),
  root_policy: z.string(),
  max_read_bytes: z.number().int().positive(),
  max_items: z.number().int().positive(),
  max_result_bytes: z.number().int().positive(),
  max_tool_calls: z.number().int().positive(),
  max_total_result_bytes: z.number().int().positive(),
  has_api_key: z.boolean(),
})

const ToolConfigMapSchema = z.object({
  web_search: WebSearchToolConfigSchema,
  local_file: LocalFileToolConfigSchema,
})
const ToolListResponseSchema = z.object({ tools: ToolConfigMapSchema })

const ValidationCheckSchema = z.object({
  check_id: z.string(),
  status: z.enum(["passed", "failed", "warning", "skipped"]),
  message: z.string(),
  duration_ms: z.number().nullable(),
  provider: z.string().nullable(),
  model: z.string().nullable(),
  details: z.record(z.string(), z.unknown()),
})
const ValidationSuiteSchema = z.object({
  name: z.string(),
  passed: z.boolean(),
  summary: z.record(z.string(), z.number().int().nonnegative()),
  results: z.array(ValidationCheckSchema),
})

export type WebSearchToolConfig = Readonly<z.infer<typeof WebSearchToolConfigSchema>>
export type LocalFileToolConfig = Readonly<z.infer<typeof LocalFileToolConfigSchema>>
export type ToolConfig = WebSearchToolConfig | LocalFileToolConfig
export type ToolConfigMap = Readonly<z.infer<typeof ToolConfigMapSchema>>
export type ValidationSuite = Readonly<z.infer<typeof ValidationSuiteSchema>>

export type WebSearchToolUpdate = Readonly<{
  readonly enabled?: boolean
  readonly provider?: SearchProvider
  readonly api_base?: string
  readonly api_key?: string
  readonly max_results?: number
  readonly max_result_bytes?: number
}>
export type LocalFileToolUpdate = Readonly<{
  readonly enabled?: boolean
  readonly max_read_bytes?: number
}>
export type ToolUpdate = WebSearchToolUpdate | LocalFileToolUpdate

function assertNever(value: never): never {
  throw new Error(`Unsupported tool key: ${String(value)}`)
}

export async function ownerRuntimeTools(): Promise<ToolConfigMap> {
  return ToolListResponseSchema.parse(await ownerRead("/api/owner/runtime/tools/")).tools
}

export function updateOwnerTool(
  toolKey: "web_search",
  update: WebSearchToolUpdate,
  csrfToken: string,
): Promise<WebSearchToolConfig>
export function updateOwnerTool(
  toolKey: "local_file",
  update: LocalFileToolUpdate,
  csrfToken: string,
): Promise<LocalFileToolConfig>
export async function updateOwnerTool(
  toolKey: ToolKey,
  update: ToolUpdate,
  csrfToken: string,
): Promise<ToolConfig> {
  const response = await ownerWrite(
    `/api/owner/runtime/tools/${toolKey}`,
    "PUT",
    csrfToken,
    update,
  )

  switch (toolKey) {
    case "web_search": {
      const parsed = z.object({
        tool_key: z.literal("web_search"),
        config: WebSearchToolConfigSchema,
      }).parse(response)
      return parsed.config
    }
    case "local_file": {
      const parsed = z.object({
        tool_key: z.literal("local_file"),
        config: LocalFileToolConfigSchema,
      }).parse(response)
      return parsed.config
    }
    default:
      return assertNever(toolKey)
  }
}

export async function verifyOwnerTool(
  toolKey: ToolKey,
  csrfToken: string,
): Promise<ValidationSuite> {
  return ValidationSuiteSchema.parse(await ownerWrite(
    `/api/owner/runtime/tools/${toolKey}/verify`,
    "POST",
    csrfToken,
  ))
}
