/**
 * The packaged Diagram Design skill provider.
 *
 * Kept free of Cordis imports so the whole shape can be exercised under plain
 * `node --test`; `index.js` supplies the context and the registrar.
 *
 * The provider never rewrites upstream content. `list()` and `get()` both read
 * the packaged `skills/diagram-design/SKILL.md` for its description, and the
 * skill directory is published as the candidate's resource base so the model
 * resolves `references/` against the real tree. The body handed to the model is
 * `lib/entry.md`, a router — see the budget note in `lib/skill.js` for why.
 *
 * @module diagram-design/lib/provider
 */

import { readFile } from 'node:fs/promises'
import { join } from 'node:path'

import {
  PROVIDER_NAME,
  buildCandidate,
  loadEntryBody,
  parseSkill,
} from './skill.js'

/**
 * Build the provider over one installed skill directory.
 *
 * @param {{ skillDirectory: string, entryFile: string | URL, onError?: (error: unknown) => void }} options
 *   `skillDirectory` is the absolute directory holding `SKILL.md` and its
 *   references; `entryFile` is the router body; `onError` receives a failure
 *   that must not take the rest of the catalog down with it.
 * @returns {{ name: string, list: Function, get: Function }} a skill provider.
 */
export function createDiagramProvider({ skillDirectory, entryFile, onError = () => {} }) {
  const skillFile = join(skillDirectory, 'SKILL.md')

  return {
    name: PROVIDER_NAME,

    /**
     * A read failure here is reported, not thrown.
     *
     * The registry catches a throwing `list()`, marks the whole catalog
     * incomplete, and `tool-skill` then publishes no skill catalog at all
     * (`if (!snapshot.complete) return decision`). One missing packaged file
     * would therefore hide every other skill the user has installed. Returning
     * no candidate keeps the rest of the catalog intact, and the failure is
     * still surfaced through `onError` and through `get()`, which throws.
     *
     * @param {{ signal?: AbortSignal }} [options]
     * @returns {Promise<readonly object[]>}
     */
    async list(options = {}) {
      try {
        const { description } = parseSkill(
          await readFile(skillFile, { encoding: 'utf8', signal: options.signal }),
          skillFile,
        )
        return [buildCandidate({ skillDirectory, description })]
      } catch (error) {
        onError(new Error(`diagram-design: cannot read the packaged skill at ${skillFile}: ${String(error)}`))
        return []
      }
    },

    /**
     * @param {object} candidate - the winning candidate from `list()`.
     * @param {{ signal?: AbortSignal }} [options]
     * @returns {Promise<object>} the skill definition, router body included.
     */
    async get(candidate, options = {}) {
      const { rank: _rank, locator: _locator, ...summary } = candidate
      const { description } = parseSkill(
        await readFile(skillFile, { encoding: 'utf8', signal: options.signal }),
        skillFile,
      )
      return { ...summary, description, content: await loadEntryBody(entryFile, options.signal) }
    },
  }
}