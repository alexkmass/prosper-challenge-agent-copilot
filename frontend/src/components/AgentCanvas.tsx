import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  applyNodeChanges,
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
import { AgentEdge } from './AgentEdge'
import { AgentNode } from './AgentNode'
import { Button } from '@/components/ui/button'
import { TooltipProvider } from '@/components/ui/tooltip'
import { LayoutGrid, Loader2, Plus, ShieldCheck } from 'lucide-react'

const nodeTypes = { agentNode: AgentNode }
const edgeTypes = { agentEdge: AgentEdge }

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
  onValidate: () => void
  validating: boolean
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
  onValidate,
  validating,
}: AgentCanvasProps) {
  const { nodes: baseNodes, edges: baseEdges } = useMemo(() => agentToFlow(config, diff), [config, diff])

  // React Flow owns the live node list: a drag mutates only the dragged node via
  // applyNodeChanges, rather than rebuilding every node object each frame (which
  // handed React Flow a fresh array mid-drag and made the whole tree flinch).
  // Manual drag positions are remembered in a ref (in-memory only, never
  // persisted) so they survive re-derivation when the graph/diff/selection
  // changes, and are cleared on agent switch or "Reorder".
  const positionsRef = useRef<Record<string, { x: number; y: number }>>({})
  const [hoveredEdgeId, setHoveredEdgeId] = useState<string | null>(null)

  // Dragging is always allowed — positions are in-memory only, so rearranging
  // for clarity is safe even while reviewing a diff.
  const seedNodes = useCallback(
    (source: Node<FlowNodeData>[]): Node<FlowNodeData>[] =>
      source.map((n) => ({
        ...n,
        position: positionsRef.current[n.id] ?? n.position,
        selected: selection?.kind === 'node' && selection.name === n.id,
        draggable: true,
      })),
    [selection],
  )

  const [nodes, setNodes] = useState<Node<FlowNodeData>[]>(() => seedNodes(baseNodes))

  // Forget manual positions on agent switch (runs before the re-seed effect below).
  useEffect(() => {
    positionsRef.current = {}
  }, [agentId])

  // Re-derive from the laid-out graph on structural/selection changes only —
  // never on a drag frame, so drags stay smooth (positionsRef is read here, not
  // a dependency).
  useEffect(() => {
    setNodes(seedNodes(baseNodes))
  }, [baseNodes, seedNodes])

  const handleNodesChange = useCallback((changes: NodeChange<Node<FlowNodeData>>[]) => {
    setNodes((nds) => applyNodeChanges(changes, nds))
    for (const change of changes) {
      if (change.type === 'position' && change.position) {
        positionsRef.current[change.id] = change.position
      }
    }
  }, [])

  const reorder = useCallback(() => {
    positionsRef.current = {}
    setNodes(seedNodes(baseNodes))
  }, [baseNodes, seedNodes])

  const edges: Edge<FlowEdgeData>[] = useMemo(() => {
    const styled = baseEdges.map((e) => {
      const isSelected = selection?.kind === 'edge' && selection.node === e.data?.sourceNode && selection.function === e.data?.function
      const isHovered = e.id === hoveredEdgeId
      return {
        ...e,
        selected: isSelected,
        zIndex: isHovered ? 1000 : undefined,
        style: { ...e.style, strokeWidth: isHovered ? 3 : (e.style?.strokeWidth ?? 1.5) },
        data: { ...e.data, hovered: isHovered } as FlowEdgeData,
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
      <TooltipProvider delayDuration={150}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          minZoom={0.3}
          maxZoom={1.5}
          proOptions={{ hideAttribution: true }}
          deleteKeyCode={null}
          nodesDraggable
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
      </TooltipProvider>
      {interactive && (
        <div className="absolute left-4 top-4 z-10 flex gap-1.5">
          <Button size="sm" onClick={onAddNode} className="shadow-sm" variant="secondary">
            <Plus className="size-4" />
            Add node
          </Button>
          <Button
            size="sm"
            onClick={reorder}
            className="shadow-sm"
            variant="secondary"
            title="Recalculate node positions"
          >
            <LayoutGrid className="size-4" />
            Reorder
          </Button>
          <Button
            size="sm"
            onClick={onValidate}
            disabled={validating}
            className="shadow-sm"
            variant="secondary"
            title="Run structural checks and an LLM design review"
          >
            {validating ? <Loader2 className="size-4 animate-spin" /> : <ShieldCheck className="size-4" />}
            {validating ? 'Validating…' : 'Validate'}
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
