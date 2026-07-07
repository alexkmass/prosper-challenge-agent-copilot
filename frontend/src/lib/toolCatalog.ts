/**
 * Hand-kept UI mirror of backend/tools/registry.py's TOOL_REGISTRY — same
 * pattern as types/agent.ts mirroring schema.py. Drives the edge inspector's
 * Tool picker (see specs/agent-tools.md).
 */
import type { AgentEdge, EdgeProperty } from '../types/agent'

export interface ToolCatalogEntry {
  key: string
  label: string
  category: string
  defaultFunction: string
  defaultDescription: string
  defaultProperties: Record<string, EdgeProperty>
  defaultRequired: string[]
}

export const TOOL_CATALOG: ToolCatalogEntry[] = [
  {
    key: 'appointment_lookup',
    label: 'Look up available appointment slots',
    category: 'Appointments',
    defaultFunction: 'find_available_slots',
    defaultDescription:
      'Call this when the caller wants to know what appointment times are open, optionally for a specific service or date.',
    defaultProperties: {
      service: { type: 'string', description: 'The service requested, e.g. general_checkup or dental_cleaning.' },
      date: { type: 'string', description: 'Preferred date (YYYY-MM-DD), if the caller mentioned one.' },
    },
    defaultRequired: [],
  },
  {
    key: 'appointment_book',
    label: 'Book an appointment slot',
    category: 'Appointments',
    defaultFunction: 'book_appointment',
    defaultDescription: 'Call this once the caller has picked a specific available slot to book.',
    defaultProperties: {
      slot_id: { type: 'string', description: 'The id of the slot the caller chose.' },
      caller_name: { type: 'string', description: "The caller's full name for the booking." },
      phone_number: { type: 'string', description: "Caller's phone number, for confirmation/reminder texts." },
      email: { type: 'string', description: "Caller's email, for confirmation/reminder emails." },
    },
    defaultRequired: ['slot_id', 'caller_name'],
  },
  {
    key: 'crm_lookup',
    label: 'Look up caller in CRM',
    category: 'CRM',
    defaultFunction: 'lookup_crm_contact',
    defaultDescription:
      "Call this as soon as you have the caller's first and last name, to check whether they're an existing contact.",
    defaultProperties: {
      first_name: { type: 'string', description: "Caller's first name." },
      last_name: { type: 'string', description: "Caller's last name." },
    },
    defaultRequired: ['first_name', 'last_name'],
  },
  {
    key: 'crm_create',
    label: 'Create caller in CRM',
    category: 'CRM',
    defaultFunction: 'create_crm_contact',
    defaultDescription:
      "Call this once you have the caller's name and insurance details, to create (or reuse) their CRM record.",
    defaultProperties: {
      first_name: { type: 'string', description: "Caller's first name." },
      last_name: { type: 'string', description: "Caller's last name." },
      insurance_id: { type: 'string', description: 'Insurance member id, if given.' },
      phone_number: { type: 'string', description: "Caller's phone number, if given." },
      email: { type: 'string', description: "Caller's email, if given." },
    },
    defaultRequired: ['first_name', 'last_name'],
  },
  {
    key: 'send_sms',
    label: 'Send confirmation text',
    category: 'Notifications',
    defaultFunction: 'send_confirmation_sms',
    defaultDescription: 'Call this to text the caller a confirmation or summary of what was just arranged.',
    defaultProperties: {
      phone_number: { type: 'string', description: 'Where to send the text, if not already known.' },
      message: { type: 'string', description: 'The text message body.' },
    },
    defaultRequired: ['message'],
  },
  {
    key: 'send_email',
    label: 'Send confirmation email',
    category: 'Notifications',
    defaultFunction: 'send_confirmation_email',
    defaultDescription: 'Call this to email the caller a confirmation or summary of what was just arranged.',
    defaultProperties: {
      email: { type: 'string', description: 'Where to send the email, if not already known.' },
      subject: { type: 'string', description: 'The email subject line.' },
      message: { type: 'string', description: 'The email body.' },
    },
    defaultRequired: ['subject', 'message'],
  },
]

export function findTool(key: string | undefined): ToolCatalogEntry | undefined {
  return TOOL_CATALOG.find((t) => t.key === key)
}

const FRESH_FUNCTION_NAME = /^go_next(_\d+)?$/

/** Prefills an edge from a tool's defaults without clobbering values already customized. */
export function resolveToolPatch(edge: AgentEdge, toolKey: string | null): Partial<AgentEdge> {
  if (!toolKey) return { tool: undefined, tool_async: false }
  const tool = findTool(toolKey)
  if (!tool) return { tool: toolKey, tool_async: false }
  return {
    tool: toolKey,
    tool_async: false,
    function: FRESH_FUNCTION_NAME.test(edge.function) ? tool.defaultFunction : edge.function,
    description: edge.description || tool.defaultDescription,
    properties: { ...tool.defaultProperties, ...edge.properties },
    required: Array.from(new Set([...(edge.required ?? []), ...tool.defaultRequired])),
  }
}
