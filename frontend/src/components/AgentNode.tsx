import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'

import type { FlowNodeData } from '../lib/agentGraph'
import { cn } from '@/lib/utils'

const statusClasses: Record<string, string> = {
  added: 'border-emerald-500 bg-emerald-50 ring-2 ring-emerald-300',
  removed: 'border-red-400 bg-red-50 opacity-60 line-through decoration-red-400',
  modified: 'border-amber-500 bg-amber-50 ring-2 ring-amber-300',
}

export function AgentNode({ data, selected }: NodeProps<Node<FlowNodeData>>) {
  return (
    <div
      className={cn(
        'w-64 rounded-lg border bg-card px-3 py-2.5 shadow-sm transition-colors',
        data.isInitial && 'border-l-4 border-l-primary',
        data.isTerminal && 'border-dashed',
        selected && 'ring-2 ring-primary',
        data.diffStatus && statusClasses[data.diffStatus],
      )}
    >
      <Handle type="target" position={Position.Top} className="!bg-muted-foreground" />
      <div className="flex items-center gap-1.5">
        {data.isInitial && (
          <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-primary">
            start
          </span>
        )}
        <div className="truncate text-sm font-medium text-card-foreground">{data.label}</div>
      </div>
      <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{data.preview || 'No instructions yet.'}</div>
      {data.isTerminal && (
        <div className="mt-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">ends call</div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-muted-foreground" />
    </div>
  )
}
