import { useCallback, useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, RefreshCw } from 'lucide-react'

import { getCall, listCalls } from '../lib/api'
import type { CallRecord, CallSummary, MetricBucket } from '../types/callLog'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'

type CallLogSheetProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

function formatClock(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function formatDuration(secs: number): string {
  if (secs < 60) return `${secs.toFixed(1)}s`
  const m = Math.floor(secs / 60)
  const s = Math.round(secs % 60)
  return `${m}m ${s}s`
}

function formatSecs(secs: number | null): string {
  return secs === null ? '—' : `${secs.toFixed(2)}s`
}

function formatCallValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function isComplexCallValue(value: unknown): boolean {
  return value !== null && typeof value === 'object'
}

function summarizeCallValue(value: unknown): string {
  if (Array.isArray(value)) {
    return `array (${value.length} item${value.length === 1 ? '' : 's'})`
  }
  if (value && typeof value === 'object') {
    const count = Object.keys(value as object).length
    return `object (${count} key${count === 1 ? '' : 's'})`
  }
  return formatCallValue(value)
}

function CollectedValue({ name, value, emphasized }: { name: string; value: unknown; emphasized?: boolean }) {
  const [open, setOpen] = useState(false)
  const complex = isComplexCallValue(value)

  if (!complex) {
    return (
      <div className="flex gap-1.5">
        <span className="text-muted-foreground">{name}:</span>
        <span className={cn(emphasized && 'font-medium', 'text-foreground')}>{formatCallValue(value)}</span>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-0.5">
      <button
        type="button"
        className="flex items-center gap-1 text-left text-foreground hover:opacity-80"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        {open ? <ChevronDown className="size-3 shrink-0" /> : <ChevronRight className="size-3 shrink-0" />}
        <span className="text-muted-foreground">{name}:</span>
        <span className={cn(emphasized && 'font-medium')}>{summarizeCallValue(value)}</span>
      </button>
      {open && (
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-muted/50 p-1.5 font-mono text-[10px] text-foreground">
          {formatCallValue(value)}
        </pre>
      )}
    </div>
  )
}

const BUCKET_LABEL: Record<MetricBucket, string> = { llm: 'LLM', stt: 'STT', tts: 'TTS' }

export function CallLogSheet({ open, onOpenChange }: CallLogSheetProps) {
  const [calls, setCalls] = useState<CallSummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<CallRecord | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refreshList = useCallback(() => {
    setLoading(true)
    listCalls()
      .then((cs) => {
        setCalls(cs)
        setError(null)
        setSelectedId((prev) => prev ?? cs[0]?.id ?? null)
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!open) return
    refreshList()
    const interval = setInterval(refreshList, 2000)
    return () => clearInterval(interval)
  }, [open, refreshList])

  useEffect(() => {
    if (!selectedId) {
      setDetail(null)
      return
    }
    let cancelled = false
    getCall(selectedId)
      .then((d) => !cancelled && setDetail(d))
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [selectedId])

  // Keep a live call's transcript/stats updating while it's still in progress.
  useEffect(() => {
    if (!open || !selectedId || detail?.status !== 'active') return
    const interval = setInterval(() => {
      getCall(selectedId)
        .then(setDetail)
        .catch(() => {})
    }, 1500)
    return () => clearInterval(interval)
  }, [open, selectedId, detail?.status])

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="flex w-full flex-col gap-0 p-0 data-[side=right]:sm:max-w-3xl">
        <SheetHeader className="border-b pr-12">
          <SheetTitle>Call log</SheetTitle>
          <SheetDescription>Every test call this session — transcript, collected data, and performance stats.</SheetDescription>
        </SheetHeader>

        {error ? (
          <p className="p-4 text-xs text-destructive">
            Couldn't reach the backend ({error}). If you just pulled in new changes, restart the backend
            (Ctrl+C, then `make run` again) and refresh.
          </p>
        ) : calls.length === 0 ? (
          <p className="p-4 text-xs text-muted-foreground">
            No test calls yet — click Test call to start one, then reopen this panel to see what it collects.
          </p>
        ) : (
          <div className="flex flex-1 overflow-hidden">
            <div className="w-56 shrink-0 overflow-y-auto border-r">
              <div className="flex items-center justify-between px-3 py-2">
                <span className="text-xs font-medium text-muted-foreground">
                  {calls.length} call{calls.length === 1 ? '' : 's'}
                </span>
                <Button size="icon-sm" variant="ghost" onClick={refreshList} disabled={loading}>
                  <RefreshCw className={cn('size-3.5', loading && 'animate-spin')} />
                </Button>
              </div>
              <Separator />
              <div className="flex flex-col">
                {calls.map((call) => (
                  <button
                    key={call.id}
                    onClick={() => setSelectedId(call.id)}
                    className={cn(
                      'flex flex-col gap-0.5 border-b px-3 py-2 text-left text-xs hover:bg-muted/60',
                      call.id === selectedId && 'bg-muted'
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-medium text-foreground">{call.caller_name ?? 'Unnamed caller'}</span>
                      {call.status === 'active' ? (
                        <Badge variant="outline" className="shrink-0 border-emerald-500 text-emerald-600">
                          Live
                        </Badge>
                      ) : (
                        <span className="shrink-0 text-muted-foreground">{formatDuration(call.duration_secs)}</span>
                      )}
                    </div>
                    <span className="truncate text-muted-foreground">{call.agent_name}</span>
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <span>{formatClock(call.started_at)}</span>
                      <span>·</span>
                      <span>{call.message_count} msgs</span>
                      {call.error_count > 0 && <span className="text-destructive">{call.error_count} err</span>}
                    </div>
                  </button>
                ))}
              </div>
            </div>

            <div className="flex-1 overflow-y-auto">
              {detail ? <CallDetail record={detail} /> : <p className="p-4 text-xs text-muted-foreground">Loading…</p>}
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}

function CallDetail({ record }: { record: CallRecord }) {
  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-foreground">
            {record.state.full_name ? String(record.state.full_name) : 'Unnamed caller'}
          </p>
          <p className="text-xs text-muted-foreground">{record.agent_name}</p>
        </div>
        {record.status === 'active' ? (
          <Badge variant="outline" className="border-emerald-500 text-emerald-600">
            Call in progress
          </Badge>
        ) : (
          <Badge variant="outline">Ended</Badge>
        )}
      </div>

      <Tabs defaultValue="transcript">
        <TabsList>
          <TabsTrigger value="transcript">Transcript</TabsTrigger>
          <TabsTrigger value="path">Path & data</TabsTrigger>
          <TabsTrigger value="stats">Stats</TabsTrigger>
        </TabsList>

        <TabsContent value="transcript" className="mt-2">
          {record.transcript.length === 0 ? (
            <p className="text-xs text-muted-foreground">Nothing said yet.</p>
          ) : (
            <div className="space-y-1.5">
              {record.transcript.map((entry, i) => (
                <div
                  key={i}
                  className={cn('flex gap-2 rounded-md border p-2 text-xs', entry.speaker === 'agent' && 'bg-muted/40')}
                >
                  <span className="w-12 shrink-0 font-medium text-foreground">
                    {entry.speaker === 'agent' ? 'Agent' : 'Caller'}
                  </span>
                  <span className="text-foreground">{entry.text}</span>
                </div>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="path" className="mt-2 space-y-4">
          <div className="space-y-1.5">
            <p className="text-xs font-medium text-foreground">Nodes visited</p>
            {record.visits.map((visit, i) => (
              <div key={i} className="rounded-md border p-2.5 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-foreground">{visit.node}</span>
                  {visit.via_function && <span className="shrink-0 text-muted-foreground">via {visit.via_function}</span>}
                </div>
                {Object.keys(visit.collected).length > 0 && (
                  <div className="mt-1.5 space-y-1">
                    {Object.entries(visit.collected).map(([k, v]) => (
                      <CollectedValue key={k} name={k} value={v} />
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          <Separator />

          <div>
            <p className="mb-1.5 text-xs font-medium text-foreground">Collected so far</p>
            {Object.keys(record.state).length === 0 ? (
              <p className="text-xs text-muted-foreground">Nothing collected yet.</p>
            ) : (
              <div className="space-y-1 rounded-md border bg-muted/40 p-2.5 text-xs">
                {Object.entries(record.state).map(([k, v]) => (
                  <CollectedValue key={k} name={k} value={v} emphasized />
                ))}
              </div>
            )}
          </div>
        </TabsContent>

        <TabsContent value="stats" className="mt-2">
          <CallStatsPanel record={record} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function CallStatsPanel({ record }: { record: CallRecord }) {
  const { stats_summary: summary, stats } = record
  const durationSecs = (record.ended_at ?? Date.now() / 1000) - record.started_at

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-2">
        <StatTile label="Total time" value={formatDuration(durationSecs)} />
        <StatTile label="Messages" value={String(summary.message_count)} />
        <StatTile
          label="Errors"
          value={String(summary.error_count)}
          tone={summary.error_count > 0 ? 'destructive' : undefined}
        />
      </div>

      <div className="space-y-2">
        {(['llm', 'stt', 'tts'] as MetricBucket[]).map((bucket) => {
          const b = summary[bucket]
          return (
            <div key={bucket} className="rounded-md border p-2.5 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-medium text-foreground">{BUCKET_LABEL[bucket]}</span>
                <span className="text-muted-foreground">
                  {b.call_count} call{b.call_count === 1 ? '' : 's'}
                </span>
              </div>
              <div className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-0.5 text-muted-foreground">
                <span>
                  Avg TTFB: <span className="text-foreground">{formatSecs(b.avg_ttfb_secs)}</span>
                </span>
                <span>
                  Total processing: <span className="text-foreground">{formatSecs(b.total_processing_secs)}</span>
                </span>
                {b.total_tokens !== null && (
                  <span>
                    Tokens: <span className="text-foreground">{b.total_tokens}</span>
                  </span>
                )}
                {b.total_tts_characters !== null && (
                  <span>
                    Characters: <span className="text-foreground">{b.total_tts_characters}</span>
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {stats.errors.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-foreground">Errors</p>
          {stats.errors.map((e, i) => (
            <div key={i} className="rounded-md border border-destructive/40 bg-destructive/5 p-2 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-foreground">{e.processor ?? 'unknown processor'}</span>
                <Badge
                  variant="outline"
                  className={e.fatal ? 'border-destructive text-destructive' : 'text-muted-foreground'}
                >
                  {e.fatal ? 'fatal' : 'recovered'}
                </Badge>
              </div>
              <p className="mt-1 text-muted-foreground">{e.error}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function StatTile({ label, value, tone }: { label: string; value: string; tone?: 'destructive' }) {
  return (
    <div className="rounded-md border p-2.5 text-center">
      <p className={cn('text-lg font-medium text-foreground', tone === 'destructive' && value !== '0' && 'text-destructive')}>
        {value}
      </p>
      <p className="text-[11px] text-muted-foreground">{label}</p>
    </div>
  )
}
