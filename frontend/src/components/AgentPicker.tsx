import { Plus } from 'lucide-react'

import type { AgentSummary } from '../lib/api'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

type AgentPickerProps = {
  agents: AgentSummary[]
  agentId: string | null
  onSelect: (id: string) => void
  onCreate: () => void
}

export function AgentPicker({ agents, agentId, onSelect, onCreate }: AgentPickerProps) {
  return (
    <div className="flex items-center gap-1.5">
      <Select value={agentId ?? undefined} onValueChange={onSelect}>
        <SelectTrigger className="w-56">
          <SelectValue placeholder="Select an agent" />
        </SelectTrigger>
        <SelectContent>
          {agents.map((a) => (
            <SelectItem key={a.id} value={a.id}>
              {a.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button variant="outline" size="icon" title="New agent" onClick={onCreate}>
        <Plus className="size-4" />
      </Button>
    </div>
  )
}
