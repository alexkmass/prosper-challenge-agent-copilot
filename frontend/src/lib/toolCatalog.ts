/**
 * Types and helpers for the edge-tool catalog served by GET /api/tools/catalog
 * (source of truth: backend/tools/registry.py).
 */
import type { AgentEdge, EdgeProperty } from '../types/agent'

export interface ToolCatalogEntry {
  key: string
  label: string
  category: string
  defaultFunction: string
  defaultDescription: string
  defaultProperties: Record<string, EdgeProperty>
  defaultRequired: string[]
}

type ToolCatalogEntryApi = {
  key: string
  label: string
  category: string
  default_function: string
  default_description: string
  default_properties: Record<string, EdgeProperty>
  default_required: string[]
}

export function mapToolCatalog(entries: ToolCatalogEntryApi[]): ToolCatalogEntry[] {
  return entries.map((entry) => ({
    key: entry.key,
    label: entry.label,
    category: entry.category,
    defaultFunction: entry.default_function,
    defaultDescription: entry.default_description,
    defaultProperties: entry.default_properties,
    defaultRequired: entry.default_required,
  }))
}

export function findTool(
  catalog: ToolCatalogEntry[],
  key: string | undefined,
): ToolCatalogEntry | undefined {
  return catalog.find((t) => t.key === key)
}

const FRESH_FUNCTION_NAME = /^go_next(_\d+)?$/

/** Prefills an edge from a tool's defaults without clobbering values already customized. */
export function resolveToolPatch(
  catalog: ToolCatalogEntry[],
  edge: AgentEdge,
  toolKey: string | null,
): Partial<AgentEdge> {
  if (!toolKey) return { tool: undefined, tool_async: false }
  const tool = findTool(catalog, toolKey)
  if (!tool) return { tool: toolKey, tool_async: false }
  return {
    tool: toolKey,
    tool_async: false,
    function: FRESH_FUNCTION_NAME.test(edge.function) ? tool.defaultFunction : edge.function,
    description: edge.description || tool.defaultDescription,
    properties: { ...tool.defaultProperties, ...edge.properties },
    required: Array.from(new Set([...(edge.required ?? []), ...tool.defaultRequired])),
  }
}
