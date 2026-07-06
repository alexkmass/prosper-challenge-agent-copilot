import type { AgentConfig } from '../types/agent'
import type { CallLogSnapshot } from '../types/callLog'
import type { Issue, MockCall } from '../types/copilot'

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

export function copilotBuild(guidelines: string): Promise<{ config: AgentConfig }> {
  return request('/api/copilot/build', { method: 'POST', body: JSON.stringify({ guidelines }) })
}

export function listMockCalls(agentId: string): Promise<MockCall[]> {
  return request(`/api/copilot/calls?agent_id=${encodeURIComponent(agentId)}`)
}

export function copilotAudit(agentId: string): Promise<{ issues: Issue[] }> {
  return request('/api/copilot/audit', {
    method: 'POST',
    body: JSON.stringify({ agent_id: agentId }),
  })
}

export function copilotFix(agentId: string, issue: Issue): Promise<{ config: AgentConfig }> {
  return request('/api/copilot/fix', {
    method: 'POST',
    body: JSON.stringify({ agent_id: agentId, issue }),
  })
}

// ---- calls --------------------------------------------------------------

export function getCallLog(): Promise<CallLogSnapshot> {
  return request('/api/calls/log')
}
