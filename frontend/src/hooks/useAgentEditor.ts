import { useCallback, useEffect, useState } from 'react'

import * as api from '../lib/api'
import type { AgentSummary } from '../lib/api'
import { blankAgent } from '../lib/agentMutations'
import type { AgentConfig } from '../types/agent'

export type Selection =
  | { kind: 'node'; name: string }
  | { kind: 'edge'; node: string; function: string }
  | null

export function useAgentEditor() {
  const [agents, setAgents] = useState<AgentSummary[]>([])
  const [agentId, setAgentId] = useState<string | null>(null)
  const [agent, setAgent] = useState<AgentConfig | null>(null)
  const [savedAgent, setSavedAgent] = useState<AgentConfig | null>(null)
  const [selection, setSelection] = useState<Selection>(null)
  const [preview, setPreview] = useState<AgentConfig | null>(null)
  const [previewMeta, setPreviewMeta] = useState<{ title: string; changes: string[] } | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refreshAgents = useCallback(async () => {
    const list = await api.listAgents()
    setAgents(list)
    return list
  }, [])

  const selectAgent = useCallback(async (id: string) => {
    setLoading(true)
    setError(null)
    setSelection(null)
    setPreview(null)
    setPreviewMeta(null)
    try {
      const config = await api.getAgent(id)
      setAgentId(id)
      setAgent(config)
      setSavedAgent(config)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshAgents()
      .then((list) => {
        if (list.length > 0) void selectAgent(list[0].id)
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const createNewAgent = useCallback(async () => {
    const created = await api.createAgent(blankAgent(`New agent ${new Date().toLocaleTimeString()}`))
    await refreshAgents()
    setAgentId(created.id)
    setAgent(created)
    setSavedAgent(created)
    setSelection(null)
    setPreview(null)
    setPreviewMeta(null)
  }, [refreshAgents])

  const mutate = useCallback((fn: (a: AgentConfig) => AgentConfig) => {
    setAgent((prev) => (prev ? fn(prev) : prev))
  }, [])

  const save = useCallback(async () => {
    if (!agentId || !agent) return
    setSaving(true)
    setError(null)
    try {
      const saved = await api.updateAgent(agentId, agent)
      setAgent(saved)
      setSavedAgent(saved)
      await refreshAgents()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      throw e
    } finally {
      setSaving(false)
    }
  }, [agentId, agent, refreshAgents])

  const proposePreview = useCallback((config: AgentConfig, meta: { title: string; changes: string[] }) => {
    setPreview(config)
    setPreviewMeta(meta)
    setSelection(null)
  }, [])

  const applyPreview = useCallback(() => {
    if (!preview) return
    setAgent(preview)
    setPreview(null)
    setPreviewMeta(null)
  }, [preview])

  const discardPreview = useCallback(() => {
    setPreview(null)
    setPreviewMeta(null)
  }, [])

  const dirty = Boolean(agent && savedAgent && JSON.stringify(agent) !== JSON.stringify(savedAgent))

  return {
    agents,
    agentId,
    agent,
    savedAgent,
    selection,
    setSelection,
    preview,
    previewMeta,
    loading,
    saving,
    error,
    dirty,
    selectAgent,
    createNewAgent,
    mutate,
    save,
    proposePreview,
    applyPreview,
    discardPreview,
  }
}

export type AgentEditor = ReturnType<typeof useAgentEditor>
