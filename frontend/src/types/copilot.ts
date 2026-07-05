/** Mirrors backend/copilot.py response shapes. */

export interface MockCallTranscriptTurn {
  speaker: 'agent' | 'caller'
  text: string
}

export interface MockCall {
  id: string
  agent_id: string
  caller_name: string
  summary: string
  transcript: MockCallTranscriptTurn[]
}

export type IssueSeverity = 'low' | 'medium' | 'high'

export interface Issue {
  call_id: string
  title: string
  description: string
  node_name: string
  severity: IssueSeverity
  evidence_quote: string
}
