import { useEffect, useMemo, useState } from 'react'
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  type Connection,
  type Edge,
  type Node,
  type NodeChange,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import type { AgentConfig } from '../types/agent'
import type { AgentDiff } from '../lib/agentDiff'
import { agentToFlow, type FlowEdgeData, type FlowNodeData } from '../lib/agentGraph'
import type { Selection } from '../hooks/useAgentEditor'
import { AgentNode } from './AgentNode'
import { Button } from '@/components/ui/button'
import { LayoutGrid, Plus } from 'lucide-react'

const nodeTypes = { agentNode: AgentNode }

type AgentCanvasProps = {
  agentId: string | null
  config: AgentConfig
  diff?: Pick<AgentDiff, 'nodeStatus' | 'edgeStatus'>
  selection: Selection
  interactive: boolean
  onSelectNode: (name: string) => void
  onSelectEdge: (node: string, fn: string) => void
  onDeselect: () => void
  onConnect: (source: string, target: string) => void
  onAddNode: () => void
}

function AgentCanvasInner({
  agentId,
  config,
  diff,
  selection,
  interactive,
  onSelectNode,
  onSelectEdge,
  onDeselect,
  onConnect,
  onAddNode,
}: AgentCanvasProps) {
  const { nodes: baseNodes, edges: baseEdges } = useMemo(() => agentToFlow(config, diff), [config, diff])

  // Manual drag positions, kept in memory only (never persisted) — cleared when
  // switching agents or when the user asks to auto-arrange again.
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({})
  const [hoveredEdgeId, setHoveredEdgeId] = useState<string | null>(null)

  useEffect(() => {
    setPositions({})
  }, [agentId])

  function handleNodesChange(changes: NodeChange<Node<FlowNodeData>>[]) {
    const moved = changes.filter((c): c is Extract<typeof c, { type: 'position' }> => c.type === 'position')
    if (moved.length === 0) return
    setPositions((prev) => {
      const next = { ...prev }
      for (const change of moved) {
        if (change.position) next[change.id] = change.position
      }
      return next
    })
  }

  const nodes: Node<FlowNodeData>[] = useMemo(
    () =>
      baseNodes.map((n) => ({
        ...n,
        position: positions[n.id] ?? n.position,
        selected: selection?.kind === 'node' && selection.name === n.id,
        draggable: interactive,
      })),
    [baseNodes, positions, selection, interactive],
  )

  const edges: Edge<FlowEdgeData>[] = useMemo(() => {
    const styled = baseEdges.map((e) => {
      const isSelected = selection?.kind === 'edge' && selection.node === e.data?.sourceNode && selection.function === e.data?.function
      const isHovered = e.id === hoveredEdgeId
      return {
        ...e,
        selected: isSelected,
        zIndex: isHovered ? 1000 : undefined,
        style: { ...e.style, strokeWidth: isHovered ? 3 : (e.style?.strokeWidth ?? 1.5) },
        labelStyle: isHovered ? { fontSize: 12, fontWeight: 600 } : { fontSize: 10 },
        labelBgStyle: { ...e.labelBgStyle, fillOpacity: isHovered ? 0.95 : (e.labelBgStyle?.fillOpacity ?? 0.7) },
      }
    })
    // Render the hovered edge last so it draws on top of anything it overlaps.
    if (hoveredEdgeId) {
      const idx = styled.findIndex((e) => e.id === hoveredEdgeId)
      if (idx >= 0) styled.push(...styled.splice(idx, 1))
    }
    return styled
  }, [baseEdges, selection, hoveredEdgeId])

  return (
    <div className="relative h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.3}
        maxZoom={1.5}
        proOptions={{ hideAttribution: true }}
        deleteKeyCode={null}
        nodesDraggable={interactive}
        nodesConnectable={interactive}
        elementsSelectable={interactive}
        onNodesChange={handleNodesChange}
        onConnect={(c: Connection) => {
          if (interactive && c.source && c.target) onConnect(c.source, c.target)
        }}
        onNodeClick={(_, node) => interactive && onSelectNode(node.id)}
        onEdgeClick={(_, edge) => {
          const data = edge.data as FlowEdgeData | undefined
          if (interactive && data) onSelectEdge(data.sourceNode, data.function)
        }}
        onEdgeMouseEnter={(_, edge) => setHoveredEdgeId(edge.id)}
        onEdgeMouseLeave={() => setHoveredEdgeId(null)}
        onPaneClick={() => interactive && onDeselect()}
      >
        <Background gap={16} size={1} />
        <Controls showInteractive={false} />
        <MiniMap pannable zoomable />
      </ReactFlow>
      {interactive && (
        <div className="absolute left-4 top-4 z-10 flex gap-1.5">
          <Button size="sm" onClick={onAddNode} className="shadow-sm" variant="secondary">
            <Plus className="size-4" />
            Add node
          </Button>
          <Button
            size="sm"
            onClick={() => setPositions({})}
            className="shadow-sm"
            variant="secondary"
            title="Recalculate node positions"
          >
            <LayoutGrid className="size-4" />
            Reorder
          </Button>
        </div>
      )}
    </div>
  )
}

export function AgentCanvas(props: AgentCanvasProps) {
  return (
    <ReactFlowProvider>
      <AgentCanvasInner {...props} />
    </ReactFlowProvider>
  )
}
