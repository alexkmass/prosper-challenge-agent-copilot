import type { Edge, Node } from '@xyflow/react'

import type { AgentConfig, AgentNode } from '../types/agent'
import type { AgentDiff, DiffStatus } from './agentDiff'

export type FlowNodeData = {
  label: string
  preview: string
  isInitial: boolean
  isTerminal: boolean
  diffStatus?: DiffStatus
}

export type FlowEdgeData = {
  diffStatus?: DiffStatus
  sourceNode: string
  function: string
  tool?: string
  toolAsync?: boolean
  hovered?: boolean
}

const NODE_WIDTH = 260
const NODE_HEIGHT = 100
const X_GAP = 160
const Y_GAP = 220

function taskPreview(node: AgentNode): string {
  const content = node.task_messages?.[0]?.content ?? ''
  return content.length > 90 ? `${content.slice(0, 90)}…` : content
}

/** BFS depth from initial_node — used for in-memory canvas layout only. */
function nodeDepths(config: AgentConfig): Map<string, number> {
  const depths = new Map<string, number>()
  const queue: string[] = [config.initial_node]
  depths.set(config.initial_node, 0)

  while (queue.length > 0) {
    const name = queue.shift()!
    const depth = depths.get(name) ?? 0
    const node = config.nodes.find((n) => n.name === name)
    for (const edge of node?.edges ?? []) {
      if (!depths.has(edge.target)) {
        depths.set(edge.target, depth + 1)
        queue.push(edge.target)
      }
    }
  }

  for (const node of config.nodes) {
    if (!depths.has(node.name)) depths.set(node.name, 0)
  }

  return depths
}

function computePosition(
  node: AgentNode,
  config: AgentConfig,
  indexInRow: number,
  rowSize: number,
): { x: number; y: number } {
  const depths = nodeDepths(config)
  const depth = depths.get(node.name) ?? 0
  const rowWidth = Math.max(rowSize - 1, 0) * (NODE_WIDTH + X_GAP)
  const x = indexInRow * (NODE_WIDTH + X_GAP) - rowWidth / 2 + 400
  const y = depth * (NODE_HEIGHT + Y_GAP) + 80
  return { x, y }
}

export function agentToFlow(
  config: AgentConfig,
  diff?: Pick<AgentDiff, 'nodeStatus' | 'edgeStatus'>,
): {
  nodes: Node<FlowNodeData>[]
  edges: Edge<FlowEdgeData>[]
} {
  const depths = nodeDepths(config)
  const byDepth = new Map<number, AgentNode[]>()

  for (const node of config.nodes) {
    const d = depths.get(node.name) ?? 0
    const row = byDepth.get(d) ?? []
    row.push(node)
    byDepth.set(d, row)
  }

  const nodes: Node<FlowNodeData>[] = config.nodes.map((node) => {
    const depth = depths.get(node.name) ?? 0
    const row = byDepth.get(depth) ?? []
    const indexInRow = row.findIndex((n) => n.name === node.name)
    const position = computePosition(node, config, indexInRow, row.length)

    return {
      id: node.name,
      type: 'agentNode',
      position,
      data: {
        label: node.name,
        preview: taskPreview(node),
        isInitial: node.name === config.initial_node,
        isTerminal: Boolean(node.end),
        diffStatus: diff?.nodeStatus.get(node.name),
      },
    }
  })

  const edges: Edge<FlowEdgeData>[] = config.nodes.flatMap((node) =>
    (node.edges ?? []).map((edge) => {
      const id = `${node.name}->${edge.target}:${edge.function}`
      const status = diff?.edgeStatus.get(id)
      return {
        id,
        source: node.name,
        target: edge.target,
        label: edge.description,
        type: 'agentEdge',
        style: EDGE_STYLES[status ?? 'unchanged'],
        data: {
          diffStatus: status,
          sourceNode: node.name,
          function: edge.function,
          tool: edge.tool,
          toolAsync: edge.tool_async,
        },
      }
    }),
  )

  return { nodes, edges }
}

const EDGE_STYLES: Record<DiffStatus | 'unchanged', { stroke: string; strokeDasharray?: string; strokeWidth?: number }> = {
  unchanged: { stroke: 'var(--muted-foreground)' },
  added: { stroke: '#10b981', strokeWidth: 2 },
  removed: { stroke: '#ef4444', strokeDasharray: '4 3', strokeWidth: 2 },
  modified: { stroke: '#f59e0b', strokeWidth: 2 },
}
