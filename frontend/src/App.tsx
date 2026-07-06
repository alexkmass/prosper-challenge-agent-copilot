import { useMemo, useState } from 'react'
import { ExternalLink, ListChecks, Sparkles } from 'lucide-react'

import { AgentCanvas } from './components/AgentCanvas'
import { AgentPicker } from './components/AgentPicker'
import { AgentSettingsPanel } from './components/AgentSettingsPanel'
import { CallLogSheet } from './components/CallLogSheet'
import { CopilotPanel } from './components/CopilotPanel'
import { DiffReviewPanel } from './components/DiffReviewPanel'
import { EdgeInspector } from './components/EdgeInspector'
import { NodeInspector } from './components/NodeInspector'
import { Button } from '@/components/ui/button'
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { useAgentEditor } from './hooks/useAgentEditor'
import { setActiveAgentId } from './lib/api'
import { diffAgents, summarizeDiff } from './lib/agentDiff'
import {
  addEdge,
  addNode,
  deleteEdge,
  deleteNode,
  renameNode,
  setInitialNode,
  setTaskMessage,
  updateEdge,
  updateNode,
} from './lib/agentMutations'
import type { AgentConfig, AgentEdge } from './types/agent'
import './App.css'

type SidebarMode = 'inspector' | 'copilot'
type PendingSwitch = { type: 'select'; id: string } | { type: 'create' }

export default function App() {
  const editor = useAgentEditor()
  const { agent, agentId, selection, preview, previewMeta } = editor
  const [sidebarMode, setSidebarMode] = useState<SidebarMode>('inspector')
  const [testCallBusy, setTestCallBusy] = useState(false)
  const [testCallError, setTestCallError] = useState<string | null>(null)
  const [callLogOpen, setCallLogOpen] = useState(false)
  const [pendingSwitch, setPendingSwitch] = useState<PendingSwitch | null>(null)
  const [switching, setSwitching] = useState(false)

  const diff = useMemo(() => (agent && preview ? diffAgents(agent, preview) : null), [agent, preview])

  const selectedNode =
    selection?.kind === 'node' ? agent?.nodes.find((n) => n.name === selection.name) : undefined
  const selectedEdgeSource =
    selection?.kind === 'edge' ? agent?.nodes.find((n) => n.name === selection.node) : undefined
  const selectedEdge =
    selection?.kind === 'edge'
      ? selectedEdgeSource?.edges?.find((e) => e.function === selection.function)
      : undefined

  function handleConnect(source: string, target: string) {
    if (!agent) return
    const { agent: next, function: fn } = addEdge(agent, source, target)
    editor.mutate(() => next)
    editor.setSelection({ kind: 'edge', node: source, function: fn })
  }

  function handleAddNode() {
    if (!agent) return
    const { agent: next, name } = addNode(agent)
    editor.mutate(() => next)
    editor.setSelection({ kind: 'node', name })
    setSidebarMode('inspector')
  }

  function handleUpdateEdge(patch: Partial<AgentEdge>) {
    if (!agent || selection?.kind !== 'edge') return
    const node = agent.nodes.find((n) => n.name === selection.node)
    const index = node?.edges?.findIndex((e) => e.function === selection.function) ?? -1
    if (index < 0) return
    editor.mutate((a) => updateEdge(a, selection.node, index, patch))
    if (patch.function && patch.function !== selection.function) {
      editor.setSelection({ kind: 'edge', node: selection.node, function: patch.function })
    }
  }

  function handleDeleteEdge() {
    if (!agent || selection?.kind !== 'edge') return
    const node = agent.nodes.find((n) => n.name === selection.node)
    const index = node?.edges?.findIndex((e) => e.function === selection.function) ?? -1
    if (index < 0) return
    editor.mutate((a) => deleteEdge(a, selection.node, index))
    editor.setSelection(null)
  }

  function handlePropose(config: AgentConfig, title: string) {
    if (!agent) return
    const d = diffAgents(agent, config)
    editor.proposePreview(config, { title, changes: summarizeDiff(d) })
  }

  async function handleSave() {
    try {
      await editor.save()
    } catch {
      // surfaced via editor.error
    }
  }

  async function handleTestCall() {
    if (!agentId) return
    // Open the tab synchronously (within the click gesture) so the browser doesn't
    // treat it as a blocked popup, then navigate it once setup finishes. Deliberately
    // no noopener/noreferrer here — /client is our own trusted page, and severing the
    // opener reference would make it impossible to navigate this handle below.
    const testCallWindow = window.open('', '_blank')
    if (!testCallWindow) {
      setTestCallError('Your browser blocked the new tab — allow pop-ups for this site and try again.')
      return
    }
    setTestCallError(null)
    setTestCallBusy(true)
    try {
      if (editor.dirty) await editor.save()
      await setActiveAgentId(agentId)
      testCallWindow.location.href = '/client'
    } catch {
      testCallWindow.close()
      // surfaced via editor.error
    } finally {
      setTestCallBusy(false)
    }
  }

  function requestSelectAgent(id: string) {
    if (id === agentId) return
    if (editor.dirty) setPendingSwitch({ type: 'select', id })
    else void editor.selectAgent(id)
  }

  function requestCreateAgent() {
    if (editor.dirty) setPendingSwitch({ type: 'create' })
    else void editor.createNewAgent()
  }

  async function resolvePendingSwitch(action: 'discard' | 'save') {
    const p = pendingSwitch
    if (!p) return
    setSwitching(true)
    try {
      if (action === 'save') await editor.save()
      setPendingSwitch(null)
      if (p.type === 'select') await editor.selectAgent(p.id)
      else await editor.createNewAgent()
    } catch {
      // save failed — surfaced via editor.error, stay on the current agent and dialog
    } finally {
      setSwitching(false)
    }
  }

  const showingPreview = Boolean(preview && previewMeta && diff)

  return (
    <div className="flex h-screen flex-col bg-background">
      <header className="flex h-14 shrink-0 items-center justify-between border-b bg-card px-4">
        <div className="flex items-center gap-3">
          <h1 className="text-sm font-semibold text-foreground">Voice Agent Builder</h1>
          <AgentPicker
            agents={editor.agents}
            agentId={agentId}
            onSelect={requestSelectAgent}
            onCreate={requestCreateAgent}
          />
        </div>
        <div className="flex items-center gap-2">
          {testCallError && <span className="text-xs text-destructive">{testCallError}</span>}
          {editor.error && !testCallError && <span className="text-xs text-destructive">{editor.error}</span>}
          {editor.dirty && !editor.error && !testCallError && (
            <span className="text-xs text-muted-foreground">Unsaved changes</span>
          )}
          <Button
            variant={sidebarMode === 'copilot' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setSidebarMode((m) => (m === 'copilot' ? 'inspector' : 'copilot'))}
          >
            <Sparkles className="size-4" />
            Copilot
          </Button>
          <Button variant="outline" size="sm" onClick={handleSave} disabled={!editor.dirty || editor.saving}>
            {editor.saving ? 'Saving…' : 'Save'}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setCallLogOpen(true)}>
            <ListChecks className="size-4" />
            Call log
          </Button>
          <Button size="sm" onClick={handleTestCall} disabled={!agentId || testCallBusy}>
            <ExternalLink className="size-4" />
            {testCallBusy ? 'Starting…' : 'Test call'}
          </Button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <main className="min-w-0 flex-1">
          {editor.loading && <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Loading…</div>}
          {!editor.loading && agent && (
            <AgentCanvas
              agentId={agentId}
              config={showingPreview && diff ? diff.merged : agent}
              diff={showingPreview && diff ? diff : undefined}
              selection={selection}
              interactive={!showingPreview}
              onSelectNode={(name) => {
                editor.setSelection({ kind: 'node', name })
                setSidebarMode('inspector')
              }}
              onSelectEdge={(node, fn) => {
                editor.setSelection({ kind: 'edge', node, function: fn })
                setSidebarMode('inspector')
              }}
              onDeselect={() => editor.setSelection(null)}
              onConnect={handleConnect}
              onAddNode={handleAddNode}
            />
          )}
        </main>

        <aside className="w-96 shrink-0 border-l bg-card">
          {showingPreview && diff && previewMeta ? (
            <DiffReviewPanel
              title={previewMeta.title}
              changes={previewMeta.changes}
              diff={diff}
              onApply={editor.applyPreview}
              onDiscard={editor.discardPreview}
            />
          ) : sidebarMode === 'copilot' && agentId && agent ? (
            <CopilotPanel agentId={agentId} agent={agent} onPropose={handlePropose} />
          ) : selection?.kind === 'node' && selectedNode && agent ? (
            <NodeInspector
              agent={agent}
              node={selectedNode}
              onRename={(newName) => {
                editor.mutate((a) => renameNode(a, selection.name, newName))
                editor.setSelection({ kind: 'node', name: newName })
              }}
              onUpdate={(patch) => editor.mutate((a) => updateNode(a, selection.name, patch))}
              onSetTaskMessage={(content) => editor.mutate((a) => setTaskMessage(a, selection.name, content))}
              onSetInitial={() => editor.mutate((a) => setInitialNode(a, selection.name))}
              onDelete={() => {
                editor.mutate((a) => deleteNode(a, selection.name))
                editor.setSelection(null)
              }}
              onSelectEdge={(fn) => editor.setSelection({ kind: 'edge', node: selection.name, function: fn })}
              onAddEdge={(target) => handleConnect(selection.name, target)}
            />
          ) : selection?.kind === 'edge' && selectedEdge && agent ? (
            <EdgeInspector
              agent={agent}
              sourceNode={selection.node}
              edge={selectedEdge}
              onUpdate={handleUpdateEdge}
              onDelete={handleDeleteEdge}
            />
          ) : agent ? (
            <AgentSettingsPanel agent={agent} onUpdate={(patch) => editor.mutate((a) => ({ ...a, ...patch }))} />
          ) : null}
        </aside>
      </div>

      <CallLogSheet open={callLogOpen} onOpenChange={setCallLogOpen} />

      <AlertDialog open={pendingSwitch !== null} onOpenChange={(open) => !open && setPendingSwitch(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Unsaved changes</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to keep editing this agent? You have unsaved changes to "{agent?.name}" that
              will be lost if you switch now.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <Button variant="outline" onClick={() => setPendingSwitch(null)} disabled={switching}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => void resolvePendingSwitch('discard')} disabled={switching}>
              Discard
            </Button>
            <Button onClick={() => void resolvePendingSwitch('save')} disabled={switching}>
              {switching ? 'Saving…' : 'Save'}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
