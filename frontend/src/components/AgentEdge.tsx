import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath, type Edge, type EdgeProps } from '@xyflow/react'
import { Wrench, Zap } from 'lucide-react'

import type { FlowEdgeData } from '../lib/agentGraph'
import { findTool } from '../lib/toolCatalog'
import { useToolCatalog } from '../hooks/useToolCatalog'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

const diffLabelClasses: Record<string, string> = {
  added: 'border-emerald-300 bg-emerald-50 text-emerald-700',
  removed: 'border-red-300 bg-red-50 text-red-700 line-through',
  modified: 'border-amber-300 bg-amber-50 text-amber-700',
}

export function AgentEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  markerEnd,
  label,
  data,
  selected,
}: EdgeProps<Edge<FlowEdgeData>>) {
  // Fan sibling edges apart: shift each one's routing (and therefore its label)
  // horizontally by its slot among the edges leaving the same source, so
  // parallel/overlapping edges stay readable — critical in the diff overlay.
  const fanCount = data?.fanCount ?? 1
  const fanIndex = data?.fanIndex ?? 0
  const fanOffset = fanCount > 1 ? (fanIndex - (fanCount - 1) / 2) * 28 : 0

  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    ...(fanOffset !== 0 ? { centerX: (sourceX + targetX) / 2 + fanOffset } : {}),
  })

  const toolCatalog = useToolCatalog()
  const tool = data?.tool ? findTool(toolCatalog, data.tool) : undefined
  const hovered = Boolean(data?.hovered)

  return (
    <>
      <BaseEdge id={id} path={edgePath} style={style} markerEnd={markerEnd} />
      <EdgeLabelRenderer>
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            zIndex: hovered ? 1000 : undefined,
          }}
          className="nodrag nopan pointer-events-none flex max-w-[220px] items-center gap-1"
        >
          {label && (
            <span
              className={cn(
                'truncate rounded border bg-background/95 px-1.5 py-0.5 shadow-sm',
                hovered ? 'text-[12px] font-semibold' : 'text-[10px]',
                data?.diffStatus ? diffLabelClasses[data.diffStatus] : 'border-border text-foreground',
              )}
            >
              {label}
            </span>
          )}
          {tool && (
            <Tooltip>
              <TooltipTrigger asChild>
                <span
                  className={cn(
                    'pointer-events-auto flex shrink-0 items-center justify-center rounded-full border bg-background p-1 text-muted-foreground shadow-sm',
                    selected && 'ring-2 ring-primary',
                  )}
                >
                  {data?.toolAsync ? <Zap className="size-3" /> : <Wrench className="size-3" />}
                </span>
              </TooltipTrigger>
              <TooltipContent side="top">
                <div className="max-w-56 text-left">
                  <div className="font-semibold">
                    {tool.label}
                    {data?.toolAsync ? ' · runs in background' : ''}
                  </div>
                  <div className="mt-0.5 text-[11px] opacity-90">{tool.defaultDescription}</div>
                </div>
              </TooltipContent>
            </Tooltip>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  )
}
