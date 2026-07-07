import { copilotBuild } from '../lib/api'
import type { AgentConfig } from '../types/agent'
import { CopilotChat } from './CopilotChat'

type CopilotBuildTabProps = {
  agent: AgentConfig
  onPropose: (config: AgentConfig, title: string, explanation: string) => void
}

export function CopilotBuildTab({ agent, onPropose }: CopilotBuildTabProps) {
  // The blank starter agent has exactly one node — anything more means there's
  // real work in progress that a generate would blow away.
  const hasContent = agent.nodes.length > 1

  return (
    <div className="flex h-full flex-col gap-3">
      <div>
        <h3 className="text-sm font-semibold text-foreground">Build from guidelines</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Describe the agent you want. The Copilot asks about anything unclear, shapes it into a solid brief, then
          builds a full node graph you review on the canvas before saving.
        </p>
      </div>

      <div className="min-h-0 flex-1">
        <CopilotChat
          mode="build"
          overwriteName={hasContent ? agent.name : null}
          placeholder="e.g. We're a dermatology clinic. Callers can book or cancel an appointment…"
          emptyHint="Tell me about the clinic and what callers should be able to do. I'll ask a couple of questions, then build it."
          generate={(brief) => copilotBuild(brief)}
          onPropose={onPropose}
        />
      </div>
    </div>
  )
}
