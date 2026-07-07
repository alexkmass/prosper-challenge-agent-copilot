import type { ValidationFinding } from '../types/copilot'

/** Turns selected validation findings into the first Improve-chat message. */
export function validationFindingsPrompt(findings: ValidationFinding[]): string {
  const blocks = findings.map((f, i) => {
    const lines = [`${i + 1}. ${f.title} (${f.severity})`, `   ${f.detail}`]
    if (f.node) {
      lines.push(`   Location: ${f.node}${f.edge ? ` · ${f.edge}` : ''}`)
    }
    if (f.suggestion) {
      lines.push(`   Suggested fix: ${f.suggestion}`)
    }
    return lines.join('\n')
  })
  return `Fix these issues:\n\n${blocks.join('\n\n')}`
}
