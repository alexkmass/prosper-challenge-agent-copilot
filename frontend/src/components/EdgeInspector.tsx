import { useMemo } from 'react'
import { Plus, Trash2, X } from 'lucide-react'

import type { AgentConfig, AgentEdge, EdgeProperty } from '../types/agent'
import { TOOL_CATALOG, findTool, resolveToolPatch } from '../lib/toolCatalog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Separator } from '@/components/ui/separator'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const NO_TOOL_VALUE = '__none__'

type PropertyRow = { name: string; type: string; description: string; required: boolean }

function toRows(edge: AgentEdge): PropertyRow[] {
  const required = new Set(edge.required ?? [])
  return Object.entries(edge.properties ?? {}).map(([name, prop]) => ({
    name,
    type: prop.type ?? 'string',
    description: prop.description ?? '',
    required: required.has(name),
  }))
}

function fromRows(rows: PropertyRow[]): { properties: Record<string, EdgeProperty>; required: string[] } {
  const properties: Record<string, EdgeProperty> = {}
  const required: string[] = []
  for (const row of rows) {
    if (!row.name.trim()) continue
    properties[row.name.trim()] = { type: row.type, description: row.description }
    if (row.required) required.push(row.name.trim())
  }
  return { properties, required }
}

type EdgeInspectorProps = {
  agent: AgentConfig
  sourceNode: string
  edge: AgentEdge
  onUpdate: (patch: Partial<AgentEdge>) => void
  onDelete: () => void
}

export function EdgeInspector({ agent, sourceNode, edge, onUpdate, onDelete }: EdgeInspectorProps) {
  const rows = useMemo(() => toRows(edge), [edge])
  const targets = agent.nodes.filter((n) => n.name !== sourceNode)
  const selectedTool = findTool(edge.tool)
  const categories = useMemo(() => Array.from(new Set(TOOL_CATALOG.map((t) => t.category))), [])
  const siblingFunctions = useMemo(
    () =>
      new Set(
        (agent.nodes.find((n) => n.name === sourceNode)?.edges ?? [])
          .map((e) => e.function)
          .filter((f) => f !== edge.function),
      ),
    [agent, sourceNode, edge.function],
  )

  function updateRows(next: PropertyRow[]) {
    onUpdate(fromRows(next))
  }

  function uniqueFunctionName(base: string): string {
    if (!siblingFunctions.has(base)) return base
    let i = 2
    while (siblingFunctions.has(`${base}_${i}`)) i++
    return `${base}_${i}`
  }

  function handleToolChange(value: string) {
    const patch = resolveToolPatch(edge, value === NO_TOOL_VALUE ? null : value)
    if (patch.function) patch.function = uniqueFunctionName(patch.function)
    onUpdate(patch)
  }

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground">Edge</h3>
        <Button variant="ghost" size="icon-sm" title="Delete edge" onClick={onDelete}>
          <Trash2 className="size-4 text-destructive" />
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        From <span className="font-medium text-foreground">{sourceNode}</span>
      </p>

      <div className="space-y-1.5">
        <Label htmlFor="edge-tool">Tool</Label>
        <Select value={edge.tool ?? NO_TOOL_VALUE} onValueChange={handleToolChange}>
          <SelectTrigger id="edge-tool" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NO_TOOL_VALUE}>No tool (plain transition)</SelectItem>
            {categories.map((category) => (
              <SelectGroup key={category}>
                <SelectLabel>{category}</SelectLabel>
                {TOOL_CATALOG.filter((t) => t.category === category).map((t) => (
                  <SelectItem key={t.key} value={t.key}>
                    {t.label}
                  </SelectItem>
                ))}
              </SelectGroup>
            ))}
          </SelectContent>
        </Select>
        {selectedTool && (
          <p className="text-xs text-muted-foreground">{selectedTool.defaultDescription}</p>
        )}
        {selectedTool && (
          <label className="flex items-start gap-1.5 pt-1 text-xs text-muted-foreground">
            <Checkbox
              checked={edge.tool_async ?? false}
              onCheckedChange={(checked) => onUpdate({ tool_async: Boolean(checked) })}
            />
            <span>
              Run in the background (don't wait for it) — only for side effects the agent
              doesn't need to react to right now, like sending a text or creating a CRM record.
            </span>
          </label>
        )}
      </div>

      <Separator />

      <div className="space-y-1.5">
        <Label htmlFor="edge-function">Function name</Label>
        <Input
          id="edge-function"
          value={edge.function}
          onChange={(e) => onUpdate({ function: e.target.value })}
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="edge-target">Target node</Label>
        <Select value={edge.target} onValueChange={(target) => onUpdate({ target })}>
          <SelectTrigger id="edge-target" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {targets.map((n) => (
              <SelectItem key={n.name} value={n.name}>
                {n.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="edge-description">When should the agent take this edge?</Label>
        <Textarea
          id="edge-description"
          rows={3}
          value={edge.description}
          onChange={(e) => onUpdate({ description: e.target.value })}
          placeholder="e.g. Caller wants to reschedule an existing appointment."
        />
      </div>

      <Separator />

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label>Information to collect</Label>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => updateRows([...rows, { name: '', type: 'string', description: '', required: false }])}
          >
            <Plus className="size-4" />
          </Button>
        </div>
        {rows.length === 0 && (
          <p className="text-xs text-muted-foreground">
            No fields — this edge is a simple routing choice with nothing to collect.
          </p>
        )}
        {rows.map((row, i) => (
          <div key={i} className="space-y-1.5 rounded-md border p-2.5">
            <div className="flex items-center gap-1.5">
              <Input
                placeholder="field_name"
                value={row.name}
                onChange={(e) => updateRows(rows.map((r, j) => (j === i ? { ...r, name: e.target.value } : r)))}
                className="h-7 text-xs"
              />
              <Select
                value={row.type}
                onValueChange={(type) => updateRows(rows.map((r, j) => (j === i ? { ...r, type } : r)))}
              >
                <SelectTrigger className="h-7 w-24 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="string">string</SelectItem>
                  <SelectItem value="number">number</SelectItem>
                  <SelectItem value="boolean">boolean</SelectItem>
                </SelectContent>
              </Select>
              <Button variant="ghost" size="icon-xs" onClick={() => updateRows(rows.filter((_, j) => j !== i))}>
                <X className="size-3.5" />
              </Button>
            </div>
            <Input
              placeholder="description"
              value={row.description}
              onChange={(e) =>
                updateRows(rows.map((r, j) => (j === i ? { ...r, description: e.target.value } : r)))
              }
              className="h-7 text-xs"
            />
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Checkbox
                checked={row.required}
                onCheckedChange={(required) =>
                  updateRows(rows.map((r, j) => (j === i ? { ...r, required: Boolean(required) } : r)))
                }
              />
              Required before taking this edge
            </label>
          </div>
        ))}
      </div>
    </div>
  )
}
