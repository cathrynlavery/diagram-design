/**
 * The packaged Diagram Design skill provider.
 *
 * Kept free of Cordis imports so the whole shape can be exercised under plain
 * `node --test`; `index.js` supplies the context and calls the registrar.
 *
 * The provider never rewrites upstream content. `list()` and `get()` both read
 * the packaged `skills/diagram-design/SKILL.md` for its description, and the
 * skill directory is published as the candidate's resource base so the model
 * resolves `references/` against the real tree. The body handed to the model is
 * `lib/entry.md`, a router, because the packaged `SKILL.md` is larger than the
 * harness is willing to put in one tool result.
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
 * @param {{ skillDirectory: string, entryFile: string | URL }} options
 *   `skillDirectory` is the absolute directory holding `SKILL.md` and its
 *   references; `entryFile` is the router body.
 * @returns {{ name: string, list: Function, get: Function }} a skill provider.
 */
export function createDiagramProvider({ skillDirectory, entryFile }) {
  const skillFile = join(skillDirectory, 'SKILL.md')

  return {
    name: PROVIDER_NAME,

    async list() {
      const { description } = parseSkill(await readFile(skillFile, 'utf8'), skillFile)
      return [buildCandidate({ skillDirectory, description })]
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
      return { ...summary, description, content: await loadEntryBody(entryFile) }
    },
  }
}