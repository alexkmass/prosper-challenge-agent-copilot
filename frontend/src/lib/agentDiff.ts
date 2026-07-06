/**
 * Computes a visual diff between the currently-saved agent and a Copilot
 * proposal: which nodes/edges are added, removed, or modified. Produces a
 * single merged AgentConfig (old + new nodes/edges) so agentToFlow can lay
 * out one graph that shows both states at once, plus status maps the canvas
 * uses to color things.
 */
import type { AgentConfig, AgentEdge, AgentNode } from '../types/agent'

export type DiffStatus = 'added' | 'removed' | 'modified' | 'unchanged'

export interface AgentDiff {
  merged: AgentConfig
  nodeStatus: Map<string, DiffStatus>
  /** keyed the same way agentToFlow ids its edges: `${source}->${target}:${function}` */
  edgeStatus: Map<string, DiffStatus>
  hasChanges: boolean
}

function nodeEquals(a: AgentNode, b: AgentNode): boolean {
  return (
    (a.task_messages?.[0]?.content ?? '') === (b.task_messages?.[0]?.content ?? '') &&
    (a.role_message ?? '') === (b.role_message ?? '') &&
    Boolean(a.end) === Boolean(b.end)
  )
}

function edgeEquals(a: AgentEdge, b: AgentEdge): boolean {
  return (
    a.description === b.description &&
    a.target === b.target &&
    JSON.stringify(a.properties ?? {}) === JSON.stringify(b.properties ?? {}) &&
    JSON.stringify(a.required ?? []) === JSON.stringify(b.required ?? [])
  )
}

function edgeId(source: string, edge: AgentEdge): string {
  return `${source}->${edge.target}:${edge.function}`
}

export function diffAgents(oldConfig: AgentConfig | null, newConfig: AgentConfig): AgentDiff {
  const oldNodes = oldConfig?.nodes ?? []
  const oldByName = new Map(oldNodes.map((n) => [n.name, n]))
  const newNames = new Set(newConfig.nodes.map((n) => n.name))

  const nodeStatus = new Map<string, DiffStatus>()
  const edgeStatus = new Map<string, DiffStatus>()
  const mergedNodes: AgentNode[] = []
  let hasChanges = false

  for (const node of newConfig.nodes) {
    const prev = oldByName.get(node.name)
    const status: DiffStatus = !prev ? 'added' : nodeEquals(prev, node) ? 'unchanged' : 'modified'
    nodeStatus.set(node.name, status)
    if (status !== 'unchanged') hasChanges = true

    const newEdgesByFn = new Map((node.edges ?? []).map((e) => [e.function, e]))
    const prevEdgesByFn = new Map((prev?.edges ?? []).map((e) => [e.function, e]))
    const mergedEdges: AgentEdge[] = []

    for (const edge of node.edges ?? []) {
      const prevEdge = prevEdgesByFn.get(edge.function)
      const eStatus: DiffStatus = !prevEdge ? 'added' : edgeEquals(prevEdge, edge) ? 'unchanged' : 'modified'
      edgeStatus.set(edgeId(node.name, edge), eStatus)
      if (eStatus !== 'unchanged') hasChanges = true
      mergedEdges.push(edge)
    }
    for (const prevEdge of prev?.edges ?? []) {
      if (!newEdgesByFn.has(prevEdge.function)) {
        edgeStatus.set(edgeId(node.name, prevEdge), 'removed')
        mergedEdges.push(prevEdge)
        hasChanges = true
      }
    }

    mergedNodes.push({ ...node, edges: mergedEdges })
  }

  for (const node of oldNodes) {
    if (!newNames.has(node.name)) {
      nodeStatus.set(node.name, 'removed')
      hasChanges = true
      for (const edge of node.edges ?? []) {
        edgeStatus.set(edgeId(node.name, edge), 'removed')
      }
      mergedNodes.push(node)
    }
  }

  const merged: AgentConfig = {
    ...newConfig,
    initial_node: newNames.has(newConfig.initial_node)
      ? newConfig.initial_node
      : (oldConfig?.initial_node ?? newConfig.initial_node),
    nodes: mergedNodes,
  }

  return { merged, nodeStatus, edgeStatus, hasChanges }
}

/** A generic, always-accurate change list derived straight from the diff — no extra LLM output required. */
export function summarizeDiff(diff: AgentDiff): string[] {
  const lines: string[] = []
  for (const [name, status] of diff.nodeStatus) {
    if (status === 'added') lines.push(`Added node "${name}"`)
    else if (status === 'removed') lines.push(`Removed node "${name}"`)
    else if (status === 'modified') lines.push(`Updated node "${name}"`)
  }
  for (const [id, status] of diff.edgeStatus) {
    const [source, rest] = id.split('->')
    const target = rest?.split(':')[0]
    const fn = rest?.split(':')[1]
    if (status === 'added') lines.push(`Added edge "${fn}" (${source} → ${target})`)
    else if (status === 'removed') lines.push(`Removed edge "${fn}" (${source} → ${target})`)
    else if (status === 'modified') lines.push(`Updated edge "${fn}" (${source} → ${target})`)
  }
  return lines
}
