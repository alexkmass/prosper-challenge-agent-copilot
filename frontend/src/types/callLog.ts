/** Mirrors backend/call_store.py's record shapes. */

export type CallStatus = 'active' | 'ended'
export type TranscriptSpeaker = 'caller' | 'agent'
export type MetricBucket = 'llm' | 'stt' | 'tts'
export type MetricKind = 'ttfb' | 'processing' | 'usage_tokens' | 'usage_chars'

/** One row in the call list (GET /api/calls). */
export interface CallSummary {
  id: string
  agent_id: string
  agent_name: string
  status: CallStatus
  started_at: number
  ended_at: number | null
  duration_secs: number
  caller_name: string | null
  message_count: number
  error_count: number
}

export interface CallVisit {
  at: number
  node: string
  via_function: string | null
  collected: Record<string, unknown>
}

export interface TranscriptEntry {
  at: number
  speaker: TranscriptSpeaker
  text: string
}

export interface LLMTokenUsage {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cache_read_input_tokens?: number | null
  cache_creation_input_tokens?: number | null
  reasoning_tokens?: number | null
}

export interface MetricEntry {
  at: number
  kind: MetricKind
  processor: string
  model: string | null
  value: number | LLMTokenUsage
}

export interface CallErrorEntry {
  at: number
  error: string
  fatal: boolean
  processor: string | null
}

export interface CallStats {
  message_count: number
  llm: MetricEntry[]
  stt: MetricEntry[]
  tts: MetricEntry[]
  errors: CallErrorEntry[]
}

export interface BucketStatsSummary {
  call_count: number
  avg_ttfb_secs: number | null
  total_processing_secs: number | null
  total_tokens: number | null
  total_tts_characters: number | null
}

export interface CallStatsSummary {
  message_count: number
  error_count: number
  fatal_error_count: number
  llm: BucketStatsSummary
  stt: BucketStatsSummary
  tts: BucketStatsSummary
}

/** Full call detail (GET /api/calls/{id}). */
export interface CallRecord {
  id: string
  agent_id: string
  agent_name: string
  status: CallStatus
  started_at: number
  ended_at: number | null
  visits: CallVisit[]
  state: Record<string, unknown>
  transcript: TranscriptEntry[]
  stats: CallStats
  stats_summary: CallStatsSummary
}
