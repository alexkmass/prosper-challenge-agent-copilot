import { useState } from 'react'
import { Star, Trash2 } from 'lucide-react'

import type { AgentConfig, AgentNode } from '../types/agent'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Separator } from '@/components/ui/separator'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

type NodeInspectorProps = {
  agent: AgentConfig
  node: AgentNode
  onRename: (newName: string) => void
  onUpdate: (patch: Partial<AgentNode>) => void
  onSetTaskMessage: (content: string) => void
  onSetInitial: () => void
  onDelete: () => void
  onSelectEdge: (fn: string) => void
  onAddEdge: (target: string) => void
}

export function NodeInspector({
  agent,
  node,
  onRename,
  onUpdate,
  onSetTaskMessage,
  onSetInitial,
  onDelete,
  onSelectEdge,
  onAddEdge,
}: NodeInspectorProps) {
  const [nameDraft, setNameDraft] = useState(node.name)
  const isInitial = agent.initial_node === node.name
  const otherNodes = agent.nodes.filter((n) => n.name !== node.name)

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground">Node</h3>
        <Button
          variant="ghost"
          size="icon-sm"
          title={isInitial ? "Can't delete the start node" : 'Delete node'}
          disabled={isInitial}
          onClick={onDelete}
        >
          <Trash2 className="size-4 text-destructive" />
        </Button>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="node-name">Name</Label>
        <Input
          id="node-name"
          value={nameDraft}
          onChange={(e) => setNameDraft(e.target.value)}
          onBlur={() => nameDraft.trim() && nameDraft !== node.name && onRename(nameDraft.trim())}
        />
      </div>

      {isInitial ? (
        <p className="rounded-md border bg-muted/50 px-2.5 py-2 text-xs text-muted-foreground">
          <Star className="mr-1 inline size-3 align-text-top" />
          The call starts here.
        </p>
      ) : (
        <Button variant="outline" size="sm" onClick={onSetInitial} className="justify-start">
          <Star className="size-3.5" />
          Make this the start node
        </Button>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="node-task">What the agent should say / do here</Label>
        <Textarea
          id="node-task"
          rows={4}
          value={node.task_messages?.[0]?.content ?? ''}
          onChange={(e) => onSetTaskMessage(e.target.value)}
          placeholder="e.g. Ask for the caller's full name and reason for the visit."
        />
      </div>

      <div className="flex items-center justify-between rounded-md border p-3">
        <div>
          <Label htmlFor="node-end">Ends the call</Label>
          <p className="text-xs text-muted-foreground">No outgoing edges — this is a terminal step.</p>
        </div>
        <Switch id="node-end" checked={Boolean(node.end)} onCheckedChange={(end) => onUpdate({ end })} />
      </div>

      <Separator />

      <div className="space-y-2">
        <Label>Outgoing edges</Label>
        {(node.edges ?? []).length === 0 && (
          <p className="text-xs text-muted-foreground">No edges yet — the caller can't leave this node.</p>
        )}
        <div className="space-y-1.5">
          {(node.edges ?? []).map((edge) => (
            <button
              key={edge.function}
              onClick={() => onSelectEdge(edge.function)}
              className="flex w-full flex-col items-start rounded-md border px-2.5 py-1.5 text-left text-xs hover:bg-accent"
            >
              <span className="font-medium text-foreground">{edge.function} → {edge.target}</span>
              <span className="text-muted-foreground">{edge.description || 'No description yet'}</span>
            </button>
          ))}
        </div>
        {otherNodes.length > 0 && (
          <Select onValueChange={(target) => onAddEdge(target)}>
            <SelectTrigger className="w-full">
              <SelectValue placeholder="+ Add edge to…" />
            </SelectTrigger>
            <SelectContent>
              {otherNodes.map((n) => (
                <SelectItem key={n.name} value={n.name}>
                  {n.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>
    </div>
  )
}
