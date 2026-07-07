import { ArrowUp, Hammer, ListChecks, Pencil, RotateCcw, Sparkles, TriangleAlert } from 'lucide-react'
import type { ChatMessage, ChatTurn, CopilotMode, Issue } from '../types/copilot'
import { useEffect, useRef, useState } from 'react'

import type { AgentConfig } from '../types/agent'
import { Button } from '@/components/ui/button'
import type { GeneratedAgent } from '../lib/api'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { copilotChat } from '../lib/api'

/** Seeds the chat with a first message (e.g. from a clicked audit issue). */
export type ChatSeed = { id: string; prompt: string; issue?: Issue }

type CopilotChatProps = {
  mode: CopilotMode
  /** Required for improve; used to attach agent context to /chat and generation. */
  agentId?: string
  /** Build only: whether generating would overwrite an agent that already has content. */
  overwriteName?: string | null
  /** Placeholder + first-line hint for the empty state. */
  placeholder: string
  emptyHint: string
  /** Optional seed that resets the thread and auto-sends a first user turn. */
  seed?: ChatSeed | null
  /** Called when the user clears the thread (e.g. to drop a parent-held seed). */
  onRestart?: () => void
  /** Called once a seed has been applied to the transcript. */
  onSeedApplied?: () => void
  /** Turns the approved brief into a proposal. Abstracts build vs. improve generation. */
  generate: (brief: string, issue?: Issue) => Promise<GeneratedAgent>
  onPropose: (config: AgentConfig, title: string, explanation: string) => void
}

export function CopilotChat({
  mode,
  agentId,
  overwriteName,
  placeholder,
  emptyHint,
  seed,
  onRestart,
  onSeedApplied,
  generate,
  onPropose,
}: CopilotChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [turn, setTurn] = useState<ChatTurn | null>(null)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [building, setBuilding] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // The issue that seeded this thread, carried into every chat + the final generate.
  const [issue, setIssue] = useState<Issue | undefined>(undefined)

  const scrollRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, sending])

  // Send one turn: append the user message, ask the Copilot to refine, append its reply.
  // Returns true when the assistant reply landed.
  async function send(
    text: string,
    seededIssue?: Issue,
    history: ChatMessage[] = messages,
  ): Promise<boolean> {
    const trimmed = text.trim()
    if (!trimmed) return false
    const nextMessages = [...history, { role: 'user' as const, content: trimmed }]
    setMessages(nextMessages)
    setInput('')
    setSending(true)
    setError(null)
    try {
      const result = await copilotChat({
        mode,
        messages: nextMessages,
        agent_id: agentId,
        issue: seededIssue ?? issue,
      })
      setMessages((m) => [...m, { role: 'assistant', content: result.reply }])
      setTurn(result)
      return true
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      return false
    } finally {
      setSending(false)
    }
  }

  function lastUserMessageIndex(msgs: ChatMessage[]): number {
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === 'user') return i
    }
    return -1
  }

  function retryLast() {
    const idx = lastUserMessageIndex(messages)
    if (idx < 0 || sending) return
    const text = messages[idx].content
    void send(text, issue, messages.slice(0, idx))
  }

  function editLast() {
    const idx = lastUserMessageIndex(messages)
    if (idx < 0 || sending) return
    setInput(messages[idx].content)
    setMessages(messages.slice(0, idx))
    setTurn(null)
    setReviewing(false)
    setError(null)
  }

  // A seed (clicked issue) resets the thread and kicks off the first turn.
  const seedId = seed?.id
  useEffect(() => {
    if (!seedId || !seed) return
    setMessages([])
    setTurn(null)
    setReviewing(false)
    setError(null)
    setIssue(seed.issue)
    void send(seed.prompt, seed.issue, []).then((ok) => {
      if (ok) onSeedApplied?.()
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seedId])

  function restart() {
    setMessages([])
    setTurn(null)
    setInput('')
    setReviewing(false)
    setError(null)
    setIssue(undefined)
    onRestart?.()
  }

  async function build() {
    if (!turn) return
    setBuilding(true)
    setError(null)
    try {
      const { config, explanation } = await generate(turn.brief, issue)
      onPropose(config, config.name ? `Copilot proposal for "${config.name}"` : 'Copilot proposal', explanation)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBuilding(false)
    }
  }

  const started = messages.length > 0 || sending
  const canBuild = Boolean(turn) && !sending

  return (
    <div className="flex h-full flex-col gap-3">
      {started && (
        <div className="flex shrink-0 justify-end">
          <Button
            variant="ghost"
            size="sm"
            onClick={restart}
            disabled={sending || building}
            className="h-7 gap-1.5 text-xs text-muted-foreground"
          >
            <RotateCcw className="size-3.5" />
            Restart chat
          </Button>
        </div>
      )}

      {/* Transcript */}
      <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
        {!started && (
          <div className="rounded-md border border-dashed bg-muted/30 p-3 text-xs text-muted-foreground">
            <Sparkles className="mb-1.5 size-4 text-primary" />
            {emptyHint}
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={cn(
              'max-w-[90%] rounded-lg px-3 py-2 text-sm',
              m.role === 'user'
                ? 'ml-auto bg-primary text-primary-foreground'
                : 'mr-auto bg-muted text-foreground',
            )}
          >
            {m.content}
          </div>
        ))}
        {sending && (
          <div className="mr-auto rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">Thinking…</div>
        )}
      </div>

      {error && (
        <div className="space-y-1.5">
          <p className="text-xs text-destructive">{error}</p>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" className="h-7 text-xs" onClick={retryLast} disabled={sending}>
              Retry
            </Button>
            <Button variant="outline" size="sm" className="h-7 gap-1 text-xs" onClick={editLast} disabled={sending}>
              <Pencil className="size-3" />
              Edit message
            </Button>
          </div>
        </div>
      )}

      {/* Plan preview: the explicit "here's what will happen" gate before generating. */}
      {reviewing && turn ? (
        <div className="space-y-3 rounded-md border bg-card p-3">
          <div className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
            <ListChecks className="size-4 text-primary" />
            {mode === 'build' ? "What I'll build" : "What I'll change"}
          </div>
          {turn.plan.length > 0 ? (
            <ul className="space-y-1 text-sm text-muted-foreground">
              {turn.plan.map((p, i) => (
                <li key={i} className="flex gap-1.5">
                  <span className="text-primary">•</span>
                  {p}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">
              I'll generate this from what we've discussed. You'll review the diff on the canvas before anything is
              saved.
            </p>
          )}
          {mode === 'build' && overwriteName && (
            <div className="flex gap-2 rounded-md border border-amber-500/40 bg-amber-50 px-2.5 py-2 text-xs text-amber-800">
              <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
              <span>
                This replaces every node and edge in <strong>"{overwriteName}"</strong>. You'll still review the diff
                before saving.
              </span>
            </div>
          )}
          <div className="flex gap-2">
            <Button className="flex-1" onClick={() => void build()} disabled={building}>
              <Hammer className="size-4" />
              {building ? 'Generating…' : mode === 'build' ? 'Build it' : 'Generate change'}
            </Button>
            <Button variant="outline" onClick={() => setReviewing(false)} disabled={building}>
              Keep iterating
            </Button>
          </div>
        </div>
      ) : (
        <>
          {canBuild && (
            <Button
              variant={turn?.ready ? 'default' : 'secondary'}
              onClick={() => setReviewing(true)}
              disabled={sending}
            >
              <Hammer className="size-4" />
              {turn?.ready
                ? mode === 'build'
                  ? 'Review & build'
                  : 'Review & apply'
                : 'Build anyway'}
            </Button>
          )}

          {/* Composer */}
          <div className="flex items-end gap-2">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  void send(input)
                }
              }}
              placeholder={placeholder}
              rows={2}
              className="min-h-0 flex-1 resize-none text-sm"
              disabled={sending}
            />
            <Button
              size="icon"
              onClick={() => void send(input)}
              disabled={sending || !input.trim()}
              aria-label="Send"
            >
              <ArrowUp className="size-4" />
            </Button>
          </div>
        </>
      )}
    </div>
  )
}
