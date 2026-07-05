import { useEffect, useState } from 'react'
import { ChevronDown, ChevronUp, ScanSearch, Wand2 } from 'lucide-react'

import { copilotAudit, copilotFix, listMockCalls } from '../lib/api'
import type { AgentConfig } from '../types/agent'
import type { Issue, MockCall } from '../types/copilot'
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
  onPropose: (config: AgentConfig, title: string) => void
}

export function CopilotImproveTab({ agentId, onPropose }: CopilotImproveTabProps) {
  const [calls, setCalls] = useState<MockCall[]>([])
  const [issues, setIssues] = useState<Issue[] | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [auditing, setAuditing] = useState(false)
  const [fixingCallId, setFixingCallId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setIssues(null)
    setError(null)

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

  async function proposeFix(issue: Issue) {
    setFixingCallId(issue.call_id)
    setError(null)
    try {
      const { config } = await copilotFix(agentId, issue)
      onPropose(config, issue.title)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setFixingCallId(null)
    }
  }

  const callById = new Map(calls.map((c) => [c.id, c]))

  return (
    <div className="flex h-full flex-col gap-3">
      <div>
        <h3 className="text-sm font-semibold text-foreground">Improve from call data</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          {calls.length > 0
            ? `${calls.length} mock call${calls.length === 1 ? '' : 's'} available for this agent.`
            : 'No mock calls for this agent yet.'}
        </p>
      </div>

      <Button onClick={runAudit} disabled={auditing || calls.length === 0} variant="secondary">
        <ScanSearch className="size-4" />
        {auditing ? 'Scanning calls…' : issues ? 'Re-scan calls' : 'Scan calls for issues'}
      </Button>

      {error && <p className="text-xs text-destructive">{error}</p>}

      {issues && issues.length === 0 && (
        <p className="text-xs text-muted-foreground">No issues found in these calls.</p>
      )}

      <div className="flex-1 space-y-2 overflow-y-auto">
        {issues?.map((issue) => {
          const call = callById.get(issue.call_id)
          const isExpanded = expanded === issue.call_id
          return (
            <div key={issue.call_id} className="rounded-md border p-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-medium text-foreground">{issue.title}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{issue.description}</p>
                </div>
                <Badge variant="outline" className={cn('shrink-0', SEVERITY_STYLE[issue.severity])}>
                  {issue.severity}
                </Badge>
              </div>

              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <Badge variant="secondary" className="text-[10px]">
                  node: {issue.node_name}
                </Badge>
                {call && (
                  <button
                    className="flex items-center gap-0.5 text-[11px] text-muted-foreground hover:text-foreground"
                    onClick={() => setExpanded(isExpanded ? null : issue.call_id)}
                  >
                    {call.caller_name}'s call {isExpanded ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
                  </button>
                )}
              </div>

              {isExpanded && call && (
                <div className="mt-2 space-y-1 rounded bg-muted/50 p-2 text-xs">
                  {call.transcript.map((turn, i) => (
                    <p key={i}>
                      <span className="font-medium text-foreground">{turn.speaker === 'agent' ? 'Agent' : 'Caller'}:</span>{' '}
                      <span className="text-muted-foreground">{turn.text}</span>
                    </p>
                  ))}
                </div>
              )}

              <Button
                size="sm"
                className="mt-2 w-full"
                onClick={() => proposeFix(issue)}
                disabled={fixingCallId !== null}
              >
                <Wand2 className="size-3.5" />
                {fixingCallId === issue.call_id ? 'Proposing fix…' : 'Propose fix'}
              </Button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
