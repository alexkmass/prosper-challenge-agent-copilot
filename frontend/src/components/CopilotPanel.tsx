import type { AgentConfig } from '../types/agent'
import type { CopilotMode } from '../types/copilot'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { CopilotBuildTab } from './CopilotBuildTab'
import type { ChatSeed } from './CopilotChat'
import { CopilotImproveTab } from './CopilotImproveTab'

type CopilotPanelProps = {
  agentId: string
  agent: AgentConfig
  onPropose: (config: AgentConfig, title: string, explanation: string) => void
  /** Controlled active tab, so outside actions (e.g. validation) can jump to Improve. */
  tab: CopilotMode
  onTabChange: (tab: CopilotMode) => void
  /** A seed pushed into the Improve chat from outside (validation findings). */
  improveSeed?: ChatSeed | null
  /** Called once the Improve tab consumes the seed, so the parent can clear it. */
  onImproveSeedConsumed?: () => void
}

export function CopilotPanel({
  agentId,
  agent,
  onPropose,
  tab,
  onTabChange,
  improveSeed,
  onImproveSeedConsumed,
}: CopilotPanelProps) {
  return (
    <Tabs
      value={tab}
      onValueChange={(v) => onTabChange(v as CopilotMode)}
      className="flex h-full flex-col gap-0"
    >
      <TabsList className="mx-4 mt-4 shrink-0">
        <TabsTrigger value="build">Build</TabsTrigger>
        <TabsTrigger value="improve">Improve</TabsTrigger>
      </TabsList>
      <TabsContent value="build" className="min-h-0 flex-1 overflow-hidden p-4">
        <CopilotBuildTab agent={agent} onPropose={onPropose} />
      </TabsContent>
      <TabsContent value="improve" className="min-h-0 flex-1 overflow-hidden p-4">
        <CopilotImproveTab
          agentId={agentId}
          onPropose={onPropose}
          externalSeed={improveSeed}
          onSeedConsumed={onImproveSeedConsumed}
        />
      </TabsContent>
    </Tabs>
  )
}
