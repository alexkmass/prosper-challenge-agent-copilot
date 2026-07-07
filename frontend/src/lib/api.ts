import type { AgentConfig } from '../types/agent'
import type { CallRecord, CallSummary } from '../types/callLog'
import type { ChatMessage, ChatTurn, CopilotMode, Issue, MockCall, ValidationFinding } from '../types/copilot'

export type AgentSummary = {
  id: string
  name: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
    ...init,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ?? `${path} failed (${res.status})`)
  }
  return res.json()
}

// ---- agents -----------------------------------------------------------

export function listAgents(): Promise<AgentSummary[]> {
  return request('/api/agents')
}

export function getAgent(agentId: string): Promise<AgentConfig> {
  return request(`/api/agents/${agentId}`)
}

export function createAgent(config: AgentConfig): Promise<AgentConfig & { id: string }> {
  return request('/api/agents', { method: 'POST', body: JSON.stringify(config) })
}

export function updateAgent(agentId: string, config: AgentConfig): Promise<AgentConfig> {
  return request(`/api/agents/${agentId}`, { method: 'PUT', body: JSON.stringify(config) })
}

export function getActiveAgentId(): Promise<{ id: string | null }> {
  return request('/api/agents/active')
}

export function setActiveAgentId(agentId: string): Promise<{ id: string }> {
  return request('/api/agents/active', { method: 'PUT', body: JSON.stringify({ id: agentId }) })
}

// ---- copilot ------------------------------------------------------------

/** A generated agent proposal: the candidate config plus a plain-English account of it. */
export type GeneratedAgent = { config: AgentConfig; explanation: string }

/** One refinement turn. `messages` is the full history (the endpoint is stateless). */
export function copilotChat(body: {
  mode: CopilotMode
  messages: ChatMessage[]
  agent_id?: string
  issue?: Issue
}): Promise<ChatTurn> {
  return request('/api/copilot/chat', { method: 'POST', body: JSON.stringify(body) })
}

export function copilotBuild(guidelines: string): Promise<GeneratedAgent> {
  return request('/api/copilot/build', { method: 'POST', body: JSON.stringify({ guidelines }) })
}

export function listMockCalls(agentId: string): Promise<MockCall[]> {
  return request(`/api/copilot/calls?agent_id=${encodeURIComponent(agentId)}`)
}

export function listToolCatalog(): Promise<
  {
    key: string
    label: string
    category: string
    default_function: string
    default_description: string
    default_properties: Record<string, { type?: string; description?: string }>
    default_required: string[]
  }[]
> {
  return request('/api/tools/catalog')
}

export function copilotAudit(agentId: string): Promise<{ issues: Issue[] }> {
  return request('/api/copilot/audit', {
    method: 'POST',
    body: JSON.stringify({ agent_id: agentId }),
  })
}

export function copilotFix(agentId: string, issue: Issue): Promise<GeneratedAgent> {
  return request('/api/copilot/fix', {
    method: 'POST',
    body: JSON.stringify({ agent_id: agentId, issue }),
  })
}

/** Generate a fix from a refined free-text brief (optionally seeded by an issue). */
export function copilotImprove(
  agentId: string,
  brief: string,
  issue?: Issue,
): Promise<GeneratedAgent> {
  return request('/api/copilot/improve', {
    method: 'POST',
    body: JSON.stringify({ agent_id: agentId, brief, issue }),
  })
}

/** Validate the current draft: deterministic structural checks + an LLM design review. */
export function copilotValidate(config: AgentConfig): Promise<{ findings: ValidationFinding[] }> {
  return request('/api/copilot/validate', { method: 'POST', body: JSON.stringify({ config }) })
}

// ---- calls --------------------------------------------------------------

export function listCalls(): Promise<CallSummary[]> {
  return request('/api/calls')
}

export function getCall(callId: string): Promise<CallRecord> {
  return request(`/api/calls/${callId}`)
}
