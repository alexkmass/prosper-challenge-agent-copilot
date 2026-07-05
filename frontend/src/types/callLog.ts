/** Mirrors backend/call_log.py's snapshot shape. */

export interface CallLogVisit {
  at: number
  node: string
  via_function: string | null
  collected: Record<string, unknown>
}

export interface CallLogSnapshot {
  active: boolean
  visits: CallLogVisit[]
  state: Record<string, unknown>
}
