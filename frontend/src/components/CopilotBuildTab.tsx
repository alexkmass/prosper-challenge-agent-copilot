import { useState } from 'react'
import { Sparkles, TriangleAlert } from 'lucide-react'

import { copilotBuild } from '../lib/api'
import type { AgentConfig } from '../types/agent'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

const PLACEHOLDER = `e.g. We're a dermatology clinic. Callers should be able to book a new appointment or cancel an existing one. For new appointments, ask if this is their first visit — first-time patients need to spell their name and give a phone number. Offer Monday 9am or Wednesday 2pm. If a caller gets frustrated or asks for a human, transfer them.`

type CopilotBuildTabProps = {
  agent: AgentConfig
  onPropose: (config: AgentConfig, title: string) => void
}

export function CopilotBuildTab({ agent, onPropose }: CopilotBuildTabProps) {
  const [guidelines, setGuidelines] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)

  // The blank starter agent has exactly one node — anything more means there's
  // real work in progress that a generate would blow away.
  const hasContent = agent.nodes.length > 1

  async function generate() {
    setBusy(true)
    setError(null)
    try {
      const { config } = await copilotBuild(guidelines)
      onPropose(config, `Built "${config.name}" from your guidelines`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  function handleGenerateClick() {
    if (!guidelines.trim()) return
    if (hasContent) setConfirmOpen(true)
    else void generate()
  }

  return (
    <div className="flex h-full flex-col gap-3">
      <div>
        <h3 className="text-sm font-semibold text-foreground">Build from guidelines</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Paste a client's natural-language instructions. The Copilot designs a full node graph — review the
          proposal on the canvas before saving.
        </p>
      </div>

      {hasContent && (
        <div className="flex gap-2 rounded-md border border-amber-500/40 bg-amber-50 px-2.5 py-2 text-xs text-amber-800">
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
          <span>
            <strong>"{agent.name}"</strong> already has a graph. Generating will replace every node and edge in it
            — you'll still review the diff before saving, but there's no getting the old graph back once you do.
          </span>
        </div>
      )}

      <Textarea
        value={guidelines}
        onChange={(e) => setGuidelines(e.target.value)}
        placeholder={PLACEHOLDER}
        rows={12}
        className="flex-1 resize-none text-sm"
      />
      {error && <p className="text-xs text-destructive">{error}</p>}
      <Button onClick={handleGenerateClick} disabled={busy || !guidelines.trim()}>
        <Sparkles className="size-4" />
        {busy ? 'Designing agent…' : 'Generate agent'}
      </Button>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Replace "{agent.name}"?</AlertDialogTitle>
            <AlertDialogDescription>
              This generates a brand new graph from your guidelines and discards every node and edge currently in
              this agent. You'll see the diff and can still discard it — but once you apply and save, the old
              graph is gone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setConfirmOpen(false)
                void generate()
              }}
            >
              Generate anyway
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
