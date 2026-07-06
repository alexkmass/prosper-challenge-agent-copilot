import { useCallback, useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'

import { getCallLog } from '../lib/api'
import type { CallLogSnapshot } from '../types/callLog'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'

type CallLogSheetProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CallLogSheet({ open, onOpenChange }: CallLogSheetProps) {
  const [snapshot, setSnapshot] = useState<CallLogSnapshot | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(() => {
    setLoading(true)
    getCallLog()
      .then((s) => {
        setSnapshot(s)
        setError(null)
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!open) return
    refresh()
    const interval = setInterval(refresh, 2000)
    return () => clearInterval(interval)
  }, [open, refresh])

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="flex w-full flex-col gap-0 p-0 sm:max-w-md">
        <SheetHeader className="border-b pr-12">
          <SheetTitle>Call log</SheetTitle>
          <SheetDescription>What the current or last test call collected, step by step.</SheetDescription>
        </SheetHeader>

        <div className="flex items-center justify-between px-4 pt-3">
          {snapshot?.active ? (
            <Badge variant="outline" className="border-emerald-500 text-emerald-600">
              Call in progress
            </Badge>
          ) : snapshot && snapshot.visits.length > 0 ? (
            <Badge variant="outline">Last call ended</Badge>
          ) : (
            <span />
          )}
          <Button size="sm" variant="ghost" onClick={refresh} disabled={loading}>
            <RefreshCw className={cn('size-3.5', loading && 'animate-spin')} />
            Refresh
          </Button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-4 pb-4 pt-2">
          {error ? (
            <p className="text-xs text-destructive">
              Couldn't reach the backend ({error}). If you just pulled in new changes, restart the backend
              (Ctrl+C, then `make run` again) and refresh.
            </p>
          ) : !snapshot || snapshot.visits.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No test call yet — click Test call to start one, then reopen this panel to see what it collects.
            </p>
          ) : (
            <>
              <div className="space-y-1.5">
                {snapshot.visits.map((visit, i) => (
                  <div key={i} className="rounded-md border p-2.5 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-foreground">{visit.node}</span>
                      {visit.via_function && (
                        <span className="shrink-0 text-muted-foreground">via {visit.via_function}</span>
                      )}
                    </div>
                    {Object.keys(visit.collected).length > 0 && (
                      <div className="mt-1.5 space-y-0.5">
                        {Object.entries(visit.collected).map(([k, v]) => (
                          <div key={k} className="flex gap-1.5">
                            <span className="text-muted-foreground">{k}:</span>
                            <span className="text-foreground">{String(v)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              <Separator />

              <div>
                <p className="mb-1.5 text-xs font-medium text-foreground">Collected so far</p>
                {Object.keys(snapshot.state).length === 0 ? (
                  <p className="text-xs text-muted-foreground">Nothing collected yet.</p>
                ) : (
                  <div className="space-y-0.5 rounded-md border bg-muted/40 p-2.5 text-xs">
                    {Object.entries(snapshot.state).map(([k, v]) => (
                      <div key={k} className="flex gap-1.5">
                        <span className="text-muted-foreground">{k}:</span>
                        <span className="font-medium text-foreground">{String(v)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
