/** Mirrors backend/agent_builder/schema.py — the agent JSON contract. */

export interface TaskMessage {
  role: string
  content: string
}

export interface EdgeProperty {
  type?: string
  enum?: string[]
  description?: string
}

export interface AgentEdge {
  function: string
  description: string
  target: string
  properties?: Record<string, EdgeProperty>
  required?: string[]
}

export interface AgentNode {
  name: string
  task_messages?: TaskMessage[]
  role_message?: string
  edges?: AgentEdge[]
  pre_actions?: unknown[]
  post_actions?: unknown[]
  end?: boolean
}

export interface AgentConfig {
  name: string
  initial_node: string
  nodes: AgentNode[]
  persona?: string
  voice_id?: string
  model?: string
}
