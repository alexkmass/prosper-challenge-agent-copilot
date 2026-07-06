import type { AgentConfig } from '../types/agent'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { CopilotBuildTab } from './CopilotBuildTab'
import { CopilotImproveTab } from './CopilotImproveTab'

type CopilotPanelProps = {
  agentId: string
  agent: AgentConfig
  onPropose: (config: AgentConfig, title: string) => void
}

export function CopilotPanel({ agentId, agent, onPropose }: CopilotPanelProps) {
  return (
    <Tabs defaultValue="build" className="flex h-full flex-col gap-0">
      <TabsList className="mx-4 mt-4 shrink-0">
        <TabsTrigger value="build">Build</TabsTrigger>
        <TabsTrigger value="improve">Improve</TabsTrigger>
      </TabsList>
      <TabsContent value="build" className="min-h-0 flex-1 overflow-y-auto p-4">
        <CopilotBuildTab agent={agent} onPropose={onPropose} />
      </TabsContent>
      <TabsContent value="improve" className="min-h-0 flex-1 overflow-y-auto p-4">
        <CopilotImproveTab agentId={agentId} onPropose={onPropose} />
      </TabsContent>
    </Tabs>
  )
}
