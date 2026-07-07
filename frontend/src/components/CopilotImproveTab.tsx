import { useEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronUp, Loader2, ScanSearch } from 'lucide-react'

import { copilotAudit, copilotImprove, listMockCalls } from '../lib/api'
import type { AgentConfig } from '../types/agent'
import type { Issue, MockCall } from '../types/copilot'
import type { ChatSeed } from './CopilotChat'
import { CopilotChat } from './CopilotChat'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

const SEVERITY_STYLE: Record<Issue['severity'], string> = {
  high: 'border-red-400 text-red-500',
  medium: 'border-amber-500 text-amber-600',
  low: 'border-muted-foreground text-muted-foreground',
}

type CopilotImproveTabProps = {
  agentId: string
  onPropose: (config: AgentConfig, title: string, explanation: string) => void
  /** A seed pushed in from outside (e.g. validation findings) that starts a chat. */
  externalSeed?: ChatSeed | null
  /** Called once the external seed has been consumed, so the parent can clear it. */
  onSeedConsumed?: () => void
}

/** Turn an audited issue into the first chat message that seeds a fix discussion. */
function seedFromIssue(issue: Issue, call?: MockCall): ChatSeed {
  const who = call ? `${call.caller_name}'s call` : 'a call'
  return {
    id: `${issue.call_id}:${issue.title}`,
    issue,
    prompt:
      `The audit flagged a problem at node "${issue.node_name}": ${issue.title}. ` +
      `${issue.description} In ${who} the caller said: "${issue.evidence_quote}". ` +
      `Let's work out how to fix this.`,
  }
}

export function CopilotImproveTab({
  agentId,
  onPropose,
  externalSeed,
  onSeedConsumed,
}: CopilotImproveTabProps) {
  const [calls, setCalls] = useState<MockCall[]>([])
  const [issues, setIssues] = useState<Issue[] | null>(null)
  const [auditing, setAuditing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [issuesOpen, setIssuesOpen] = useState(true)
  const [seed, setSeed] = useState<ChatSeed | null>(null)
  const prevAgentIdRef = useRef<string | undefined>(undefined)

  const activeSeed = externalSeed ?? seed

  useEffect(() => {
    let cancelled = false
    setIssues(null)
    setError(null)

    // Clear chat seed only when switching agents — not on first mount (would wipe
    // a validation seed handed in at the same time).
    if (prevAgentIdRef.current !== undefined && prevAgentIdRef.current !== agentId) {
      setSeed(null)
    }
    prevAgentIdRef.current = agentId

    listMockCalls(agentId)
      .then(async (loadedCalls) => {
        if (cancelled) return
        setCalls(loadedCalls)
        if (loadedCalls.length === 0) return
        // Auto-run the audit — detecting issues shouldn't require an extra click.
        setAuditing(true)
        try {
          const { issues } = await copilotAudit(agentId)
          if (!cancelled) setIssues(issues)
        } catch (e) {
          if (!cancelled) setError(e instanceof Error ? e.message : String(e))
        } finally {
          if (!cancelled) setAuditing(false)
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      })

    return () => {
      cancelled = true
    }
  }, [agentId])

  async function runAudit() {
    setAuditing(true)
    setError(null)
    try {
      const { issues } = await copilotAudit(agentId)
      setIssues(issues)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setAuditing(false)
    }
  }

  const callById = new Map(calls.map((c) => [c.id, c]))

  function discussIssue(issue: Issue) {
    const base = seedFromIssue(issue, callById.get(issue.call_id))
    // Unique id so re-clicking the same issue after a restart still seeds the chat.
    setSeed({ ...base, id: `${base.id}:${Date.now()}` })
    setIssuesOpen(false)
  }

  return (
    <div className="flex h-full flex-col gap-3">
      <div>
        <h3 className="text-sm font-semibold text-foreground">Improve this agent</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Tell the Copilot what to change, or pick a detected issue below to work through it. It refines the change
          with you, then proposes an edit you review on the canvas.
        </p>
      </div>

      {/* Detected issues — automatic, collapsible. Clicking one seeds the chat. */}
      {calls.length > 0 && (
        <div className="shrink-0 rounded-md border">
          <button
            className="flex w-full items-center justify-between px-3 py-2 text-xs font-medium text-foreground"
            onClick={() => setIssuesOpen((o) => !o)}
          >
            <span className="flex items-center gap-1.5">
              {auditing ? <Loader2 className="size-3.5 animate-spin" /> : <ScanSearch className="size-3.5" />}
              Detected issues
              {issues && (
                <Badge variant="secondary" className="text-[10px]">
                  {issues.length}
                </Badge>
              )}
            </span>
            {issuesOpen ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
          </button>

          {issuesOpen && (
            <div className="max-h-52 space-y-1.5 overflow-y-auto border-t px-2 py-2">
              {auditing && !issues && <p className="px-1 text-xs text-muted-foreground">Scanning calls…</p>}
              {issues && issues.length === 0 && (
                <p className="px-1 text-xs text-muted-foreground">No issues found in these calls.</p>
              )}
              {issues?.map((issue) => {
                const call = callById.get(issue.call_id)
                return (
                  <button
                    key={`${issue.call_id}:${issue.title}`}
                    onClick={() => discussIssue(issue)}
                    className="w-full rounded border bg-card p-2 text-left transition-colors hover:bg-accent"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-xs font-medium text-foreground">{issue.title}</p>
                      <Badge variant="outline" className={cn('shrink-0 text-[10px]', SEVERITY_STYLE[issue.severity])}>
                        {issue.severity}
                      </Badge>
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
                      <Badge variant="secondary" className="text-[10px]">
                        {issue.node_name}
                      </Badge>
                      {call && <span>{call.caller_name}'s call</span>}
                    </div>
                  </button>
                )
              })}
              <Button
                onClick={runAudit}
                disabled={auditing}
                variant="ghost"
                size="sm"
                className="w-full text-xs text-muted-foreground"
              >
                {auditing ? 'Scanning…' : 'Re-scan calls'}
              </Button>
            </div>
          )}
        </div>
      )}

      {error && <p className="text-xs text-destructive">{error}</p>}

      <div className="min-h-0 flex-1">
        <CopilotChat
          mode="improve"
          agentId={agentId}
          seed={activeSeed}
          onRestart={() => {
            setSeed(null)
            onSeedConsumed?.()
          }}
          onSeedApplied={onSeedConsumed}
          placeholder="e.g. The clinic wants callers to be able to reschedule, not just book or cancel…"
          emptyHint="Describe what you'd like to change about this agent — or click a detected issue above. I'll refine it with you before proposing an edit."
          generate={(brief, issue) => copilotImprove(agentId, brief, issue)}
          onPropose={onPropose}
        />
      </div>
    </div>
  )
}
