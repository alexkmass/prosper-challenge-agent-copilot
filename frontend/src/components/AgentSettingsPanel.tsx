import type { AgentConfig } from '../types/agent'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const MODELS = ['gpt-4o', 'gpt-4o-mini', 'gpt-4.1', 'gpt-4.1-mini']

type AgentSettingsPanelProps = {
  agent: AgentConfig
  onUpdate: (patch: Partial<AgentConfig>) => void
}

export function AgentSettingsPanel({ agent, onUpdate }: AgentSettingsPanelProps) {
  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      <div>
        <h3 className="text-sm font-semibold text-foreground">Agent settings</h3>
        <p className="text-xs text-muted-foreground">Click a node or edge on the canvas to edit it.</p>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="agent-name">Name</Label>
        <Input id="agent-name" value={agent.name} onChange={(e) => onUpdate({ name: e.target.value })} />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="agent-persona">Persona</Label>
        <Textarea
          id="agent-persona"
          rows={5}
          value={agent.persona ?? ''}
          onChange={(e) => onUpdate({ persona: e.target.value })}
          placeholder="Global instructions applied to every node — tone, constraints, who the agent is."
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="agent-model">LLM model</Label>
        <Select value={agent.model ?? 'gpt-4o'} onValueChange={(model) => onUpdate({ model })}>
          <SelectTrigger id="agent-model" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {MODELS.map((m) => (
              <SelectItem key={m} value={m}>
                {m}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="agent-voice">ElevenLabs voice ID</Label>
        <Input
          id="agent-voice"
          value={agent.voice_id ?? ''}
          onChange={(e) => onUpdate({ voice_id: e.target.value })}
        />
        <p className="text-xs text-muted-foreground">Default: 21m00Tcm4TlvDq8ikWAM (Rachel)</p>
      </div>
    </div>
  )
}
