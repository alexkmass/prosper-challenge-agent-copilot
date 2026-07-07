import { useEffect, useMemo, useState } from 'react'
import { CheckCircle2, Cog, Loader2, MessagesSquare, Sparkles, X } from 'lucide-react'

import type { ValidationFinding, ValidationSeverity } from '../types/copilot'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { cn } from '@/lib/utils'

const SEVERITY_STYLE: Record<ValidationSeverity, string> = {
  error: 'border-red-400 text-red-500',
  warning: 'border-amber-500 text-amber-600',
  info: 'border-muted-foreground text-muted-foreground',
}

const SEVERITY_ORDER: Record<ValidationSeverity, number> = { error: 0, warning: 1, info: 2 }

type ValidationPanelProps = {
  loading: boolean
  findings: ValidationFinding[]
  error: string | null
  onClose: () => void
  onSelectNode: (node: string) => void
  onSendToChat: (findings: ValidationFinding[]) => void
}

export function ValidationPanel({
  loading,
  findings,
  error,
  onClose,
  onSelectNode,
  onSendToChat,
}: ValidationPanelProps) {
  const sorted = useMemo(
    () => [...findings].sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]),
    [findings],
  )
  const [selected, setSelected] = useState<Set<number>>(() => new Set())

  // Default: errors and warnings checked; info left unchecked.
  useEffect(() => {
    setSelected(new Set(sorted.map((f, i) => i).filter((i) => sorted[i].severity !== 'info')))
  }, [sorted])

  const errors = findings.filter((f) => f.severity === 'error').length
  const warnings = findings.filter((f) => f.severity === 'warning').length
  const selectedFindings = sorted.filter((_, i) => selected.has(i))

  function toggle(index: number) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })
  }

  function setAll(checked: boolean) {
    setSelected(checked ? new Set(sorted.map((_, i) => i)) : new Set())
  }

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-foreground">Validation</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Structural checks plus an LLM design review of the current draft.
          </p>
        </div>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground" aria-label="Close">
          <X className="size-4" />
        </button>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          Running checks and design review…
        </div>
      )}

      {error && <p className="text-xs text-destructive">{error}</p>}

      {!loading && !error && findings.length === 0 && (
        <div className="flex items-center gap-2 rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          <CheckCircle2 className="size-4" />
          No issues found — this agent looks good to go.
        </div>
      )}

      {!loading && findings.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {errors > 0 && (
            <Badge variant="outline" className="border-red-400 text-red-500">
              {errors} error{errors === 1 ? '' : 's'}
            </Badge>
          )}
          {warnings > 0 && (
            <Badge variant="outline" className="border-amber-500 text-amber-600">
              {warnings} warning{warnings === 1 ? '' : 's'}
            </Badge>
          )}
        </div>
      )}

      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto">
        {sorted.length > 0 && (
          <div className="flex items-center justify-end gap-2 text-[11px] text-muted-foreground">
            <button type="button" className="hover:text-foreground" onClick={() => setAll(true)}>
              Select all
            </button>
            <span>·</span>
            <button type="button" className="hover:text-foreground" onClick={() => setAll(false)}>
              Clear
            </button>
          </div>
        )}
        {sorted.map((f, i) => (
          <div
            key={i}
            className={cn(
              'flex gap-2.5 rounded-md border p-3 transition-colors',
              selected.has(i) ? 'border-primary/40 bg-primary/5' : 'hover:bg-muted/40',
            )}
          >
            <Checkbox
              checked={selected.has(i)}
              onCheckedChange={() => toggle(i)}
              className="mt-0.5"
              aria-label={`Include "${f.title}" in Improve chat`}
            />
            <div className="min-w-0 flex-1">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-medium text-foreground">{f.title}</p>
                <Badge variant="outline" className={cn('shrink-0', SEVERITY_STYLE[f.severity])}>
                  {f.severity}
                </Badge>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">{f.detail}</p>
              {f.suggestion && (
                <p className="mt-1.5 text-xs text-foreground">
                  <span className="font-medium">Suggestion: </span>
                  {f.suggestion}
                </p>
              )}
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <Badge variant="secondary" className="gap-1 text-[10px]">
                  {f.source === 'llm' ? <Sparkles className="size-2.5" /> : <Cog className="size-2.5" />}
                  {f.source === 'llm' ? 'design review' : 'structural'}
                </Badge>
                {f.node && (
                  <button
                    type="button"
                    className="text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                    onClick={() => onSelectNode(f.node!)}
                  >
                    {f.node}
                    {f.edge ? ` · ${f.edge}` : ''}
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {!loading && findings.length > 0 && (
        <div className="mt-auto border-t pt-4">
          <Button
            className="w-full"
            disabled={selectedFindings.length === 0}
            onClick={() => onSendToChat(selectedFindings)}
          >
            <MessagesSquare className="size-4" />
            {selectedFindings.length > 0
              ? `Fix ${selectedFindings.length} in Improve chat`
              : 'Select findings to fix'}
          </Button>
          <p className="mt-1.5 text-center text-[11px] text-muted-foreground">
            Hands these to the Copilot to work through and propose a fix.
          </p>
        </div>
      )}
    </div>
  )
}
