/**
 * DeepSeek Harness host for Diagram Design.
 *
 * Two registrations, no tools, no hooks, no config:
 *
 * 1. A packaged skill provider over the repository's own
 *    `skills/diagram-design/` tree. The skill's name and routing description are
 *    parsed from the upstream `SKILL.md` at read time rather than restated here,
 *    and the directory is handed to DSH as the skill's `resourceBase` so the model
 *    resolves `references/` against it. Nothing in that tree is copied,
 *    translated or modified.
 *
 * 2. The six slash commands, registered with DSH's human-command registry. Each
 *    handler steers the agent with its instructions; a command result goes to the
 *    UI, not to the model, so the handler returns `{kind:'success'}` and lets
 *    `agent.steer` carry the text.
 *
 * The body sent to the model is `lib/entry.md`, not `SKILL.md`, because DSH's base
 * bundle prunes any `tool/result` over 8,192 characters and `SKILL.md` is 29,706
 * bytes. The router names the sections and reference files the model should read,
 * and the real specification stays on disk. See `docs/adr/0013-deepseek-harness-host.md`.
 *
 * @module diagram-design
 */
import { fileURLToPath } from 'node:url'

import { registerCommands } from './lib/commands.js'
import { createDiagramProvider } from './lib/provider.js'

/** Cordis plugin name. Distinct from the skill provider's name on purpose. */
export const name = 'diagram-design'

/** Services this plugin needs. Both ship in the DSH base bundle. */
export const inject = ['skills', 'commands']

/**
 * Register the skill provider and the six commands.
 *
 * Both registrations store themselves as fiber effects, so Cordis disposes them
 * on unload without an explicit teardown here.
 *
 * @param {import('@deepseek-ai/cordis').Context} ctx
 */
export function apply(ctx) {
  const skillDirectory = fileURLToPath(new URL('./skills/diagram-design/', import.meta.url))
  const entryFile = fileURLToPath(new URL('./lib/entry.md', import.meta.url))

  ctx.skills.registerProvider(() => createDiagramProvider({ skillDirectory, entryFile }))
  registerCommands(ctx, { skillDirectory })
}

export default { name, inject, apply }