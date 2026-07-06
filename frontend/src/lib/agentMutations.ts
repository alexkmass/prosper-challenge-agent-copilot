/**
 * Pure, immutable edits to an AgentConfig. Nodes are identified by `name`
 * (the schema has no separate id) — renameNode is responsible for keeping
 * every reference (edge targets, initial_node) in sync.
 */
import type { AgentConfig, AgentEdge, AgentNode } from '../types/agent'

function uniqueName(base: string, taken: Set<string>): string {
  if (!taken.has(base)) return base
  let i = 2
  while (taken.has(`${base}_${i}`)) i++
  return `${base}_${i}`
}

export function blankAgent(name = 'New agent'): AgentConfig {
  return {
    name,
    persona: 'You are a helpful, warm assistant. Replies are spoken aloud, so keep them short and avoid lists or emojis.',
    voice_id: '21m00Tcm4TlvDq8ikWAM',
    model: 'gpt-4o',
    initial_node: 'start',
    nodes: [
      {
        name: 'start',
        task_messages: [{ role: 'developer', content: 'Greet the caller and ask how you can help.' }],
        edges: [],
        end: true,
      },
    ],
  }
}

export function updateMeta(agent: AgentConfig, patch: Partial<AgentConfig>): AgentConfig {
  return { ...agent, ...patch }
}

export function addNode(agent: AgentConfig): { agent: AgentConfig; name: string } {
  const name = uniqueName('new_node', new Set(agent.nodes.map((n) => n.name)))
  const node: AgentNode = {
    name,
    task_messages: [{ role: 'developer', content: '' }],
    edges: [],
    end: true,
  }
  return { agent: { ...agent, nodes: [...agent.nodes, node] }, name }
}

export function deleteNode(agent: AgentConfig, name: string): AgentConfig {
  if (agent.initial_node === name) return agent // never delete the start node
  const nodes = agent.nodes
    .filter((n) => n.name !== name)
    .map((n) => ({ ...n, edges: (n.edges ?? []).filter((e) => e.target !== name) }))
  return { ...agent, nodes }
}

export function updateNode(agent: AgentConfig, name: string, patch: Partial<AgentNode>): AgentConfig {
  return {
    ...agent,
    nodes: agent.nodes.map((n) => (n.name === name ? { ...n, ...patch } : n)),
  }
}

export function setTaskMessage(agent: AgentConfig, name: string, content: string): AgentConfig {
  return updateNode(agent, name, { task_messages: [{ role: 'developer', content }] })
}

export function renameNode(agent: AgentConfig, oldName: string, newName: string): AgentConfig {
  const trimmed = newName.trim()
  if (!trimmed || trimmed === oldName) return agent
  if (agent.nodes.some((n) => n.name === trimmed)) return agent // no-op on collision

  const nodes = agent.nodes.map((n) => {
    const withRenamedSelf = n.name === oldName ? { ...n, name: trimmed } : n
    const edges = (withRenamedSelf.edges ?? []).map((e) =>
      e.target === oldName ? { ...e, target: trimmed } : e,
    )
    return { ...withRenamedSelf, edges }
  })

  return {
    ...agent,
    initial_node: agent.initial_node === oldName ? trimmed : agent.initial_node,
    nodes,
  }
}

export function setInitialNode(agent: AgentConfig, name: string): AgentConfig {
  return { ...agent, initial_node: name }
}

export function addEdge(
  agent: AgentConfig,
  sourceNode: string,
  target: string,
): { agent: AgentConfig; function: string } {
  const takenFns = new Set(
    (agent.nodes.find((n) => n.name === sourceNode)?.edges ?? []).map((e) => e.function),
  )
  const edge: AgentEdge = {
    function: uniqueName('go_next', takenFns),
    description: '',
    target,
    properties: {},
    required: [],
  }
  // `end` and edges are mutually exclusive (AgentBuilder rejects a node with
  // both) — a source node gaining its first edge can no longer be terminal.
  const next = updateNode(agent, sourceNode, {
    edges: [...(agent.nodes.find((n) => n.name === sourceNode)?.edges ?? []), edge],
    end: false,
  })
  return { agent: next, function: edge.function }
}

export function updateEdge(
  agent: AgentConfig,
  sourceNode: string,
  index: number,
  patch: Partial<AgentEdge>,
): AgentConfig {
  return updateNode(agent, sourceNode, {
    edges: (agent.nodes.find((n) => n.name === sourceNode)?.edges ?? []).map((e, i) =>
      i === index ? { ...e, ...patch } : e,
    ),
  })
}

export function deleteEdge(agent: AgentConfig, sourceNode: string, index: number): AgentConfig {
  return updateNode(agent, sourceNode, {
    edges: (agent.nodes.find((n) => n.name === sourceNode)?.edges ?? []).filter((_, i) => i !== index),
  })
}
