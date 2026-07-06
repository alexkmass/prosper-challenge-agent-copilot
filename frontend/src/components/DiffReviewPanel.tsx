import { Check, X } from 'lucide-react'

import type { AgentDiff } from '../lib/agentDiff'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

type DiffReviewPanelProps = {
  title: string
  changes: string[]
  diff: AgentDiff
  onApply: () => void
  onDiscard: () => void
}

export function DiffReviewPanel({ title, changes, diff, onApply, onDiscard }: DiffReviewPanelProps) {
  const added = [...diff.nodeStatus.values()].filter((s) => s === 'added').length
  const removed = [...diff.nodeStatus.values()].filter((s) => s === 'removed').length
  const modified = [...diff.nodeStatus.values()].filter((s) => s === 'modified').length

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      <div>
        <h3 className="text-sm font-semibold text-foreground">Copilot proposal</h3>
        <p className="mt-1 text-sm text-foreground">{title}</p>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {added > 0 && (
          <Badge variant="outline" className="border-emerald-500 text-emerald-600">
            +{added} node{added === 1 ? '' : 's'}
          </Badge>
        )}
        {modified > 0 && (
          <Badge variant="outline" className="border-amber-500 text-amber-600">
            {modified} modified
          </Badge>
        )}
        {removed > 0 && (
          <Badge variant="outline" className="border-red-400 text-red-500">
            -{removed} node{removed === 1 ? '' : 's'}
          </Badge>
        )}
        {!diff.hasChanges && <Badge variant="outline">No changes</Badge>}
      </div>

      {changes.length > 0 && (
        <ul className="space-y-1.5 text-sm text-muted-foreground">
          {changes.map((c, i) => (
            <li key={i} className="flex gap-1.5">
              <span className="text-primary">•</span>
              {c}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-auto flex gap-2 border-t pt-4">
        <Button onClick={onApply} className="flex-1" disabled={!diff.hasChanges}>
          <Check className="size-4" />
          Apply
        </Button>
        <Button onClick={onDiscard} variant="outline" className="flex-1">
          <X className="size-4" />
          Discard
        </Button>
      </div>
    </div>
  )
}
