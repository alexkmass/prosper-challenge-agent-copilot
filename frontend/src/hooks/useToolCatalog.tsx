import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

import { listToolCatalog } from '../lib/api'
import { mapToolCatalog, type ToolCatalogEntry } from '../lib/toolCatalog'

const ToolCatalogContext = createContext<ToolCatalogEntry[]>([])

export function ToolCatalogProvider({ children }: { children: ReactNode }) {
  const [catalog, setCatalog] = useState<ToolCatalogEntry[]>([])

  useEffect(() => {
    let cancelled = false
    listToolCatalog()
      .then((entries) => {
        if (!cancelled) setCatalog(mapToolCatalog(entries))
      })
      .catch(() => {
        // Edge inspector degrades to an empty tool list; save validation still runs server-side.
      })
    return () => {
      cancelled = true
    }
  }, [])

  return <ToolCatalogContext.Provider value={catalog}>{children}</ToolCatalogContext.Provider>
}

export function useToolCatalog(): ToolCatalogEntry[] {
  return useContext(ToolCatalogContext)
}
