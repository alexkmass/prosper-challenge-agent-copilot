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

export type CopilotMode = 'build' | 'improve'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

/** One refinement turn from POST /api/copilot/chat. */
export interface ChatTurn {
  reply: string
  /** The accumulated, self-contained brief that will feed generation. */
  brief: string
  /** True once the brief is complete enough to build from. */
  ready: boolean
  /** Plain-language bullets of what building will do (present when ready). */
  plan: string[]
}

export type ValidationSeverity = 'error' | 'warning' | 'info'

/** One finding from POST /api/copilot/validate. */
export interface ValidationFinding {
  severity: ValidationSeverity
  title: string
  detail: string
  /** Node the finding is localized to, if any. */
  node?: string | null
  /** Edge function within that node, if any. */
  edge?: string | null
  /** `manual` = deterministic structural check; `llm` = design review. */
  source: 'manual' | 'llm'
  /** How to fix it — LLM findings carry this; manual ones don't. */
  suggestion?: string | null
}
