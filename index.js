/**
 * DeepSeek Harness host for Diagram Design.
 *
 * `apply()` registers two things and nothing else: a packaged skill provider
 * over the repository's own `skills/diagram-design/` tree, and the six slash
 * commands from `commands/`. No tools, no hooks, no config.
 *
 * Nothing in the skill tree is copied, translated, or patched. The skill's name
 * and routing description are parsed from the upstream `SKILL.md` at read time
 * rather than restated here, and the directory is handed to DSH as the skill's
 * `resourceBase` so the model resolves `references/` against it.
 *
 * The body sent to the model is `lib/entry.md`, not `SKILL.md`. The reason is in
 * `lib/skill.js`: inlining 29,706 characters costs roughly 7,400 tokens on every
 * load, and a result that size is later reduced to its opening and closing when
 * the session compacts, which removes sections 4 to 11 from the history. See
 * `docs/adr/0013-deepseek-harness-host.md`.
 *
 * @module diagram-design
 */
import { watch } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { registerCommands } from './lib/commands.js'
import { createDiagramProvider } from './lib/provider.js'

/** Cordis plugin name. Distinct from the skill provider's name on purpose. */
export const name = 'diagram-design'

/** Services this plugin needs. Both ship in the DSH base bundle. */
export const inject = ['skills', 'commands']

/**
 * Watch the two files whose contents reach the model, and invalidate the skill
 * catalog when they change.
 *
 * The registry caches the result of `list()`, which is where the description
 * lives, while `get()` reads live. Without this the description goes stale on an
 * editable install — `dsh plugin add ~/code/diagram-design` — while the body
 * stays fresh. The packaged files sit outside every filesystem-provider root, so
 * nothing else would notice the change.
 *
 * @param {() => void} onChange
 * @returns {() => void} disposer.
 */
function watchPackagedFiles(onChange) {
  const watchers = []
  let timer
  const fire = () => {
    clearTimeout(timer)
    // Editors write in bursts; coalesce so one save is one invalidation.
    timer = setTimeout(onChange, 200)
  }
  for (const target of [
    new URL('./skills/diagram-design/SKILL.md', import.meta.url),
    new URL('./lib/entry.md', import.meta.url),
  ]) {
    try {
      // `persistent: false` so a watcher never holds the process open on its
      // own; the fiber disposer closes it explicitly.
      watchers.push(watch(fileURLToPath(target), fire, { persistent: false }))
    } catch {
      // A file that cannot be watched is not a reason to fail plugin load; the
      // catalog refreshes on the next restart instead.
    }
  }
  return () => {
    clearTimeout(timer)
    for (const watcher of watchers) watcher.close()
  }
}

/**
 * Register the skill provider and the six commands.
 *
 * @param {import('@deepseek-ai/cordis').Context} ctx
 */
export function apply(ctx) {
  const skillDirectory = fileURLToPath(new URL('./skills/diagram-design/', import.meta.url))
  const entryFile = fileURLToPath(new URL('./lib/entry.md', import.meta.url))

  ctx.skills.registerProvider(control => {
    const provider = createDiagramProvider({
      skillDirectory,
      entryFile,
      // A provider that cannot read its own skill must not take the whole
      // catalog down: the registry treats a throwing `list()` as an incomplete
      // catalog and publishes no skills at all.
      onError: error => ctx.logger.warn(String(error)),
    })
    ctx.effect(
      () => watchPackagedFiles(() => control.invalidate()),
      'diagram-design: packaged file watcher',
    )
    return provider
  })

  registerCommands(ctx, { skillDirectory })
}

export default { name, inject, apply }