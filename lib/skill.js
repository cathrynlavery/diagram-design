/**
 * Pure helpers for the Diagram Design skill provider.
 *
 * Nothing here imports Cordis or DSH, so the tests run under plain `node --test`
 * with no harness installed and no build step.
 *
 * The packaged `skills/diagram-design/` tree is upstream and stays byte-identical.
 * This module reads it; it never restates it. The one body it does supply is
 * `lib/entry.md`, a router short enough to survive the tool-result pruner that
 * the default DSH composition mounts at 8,192 characters.
 *
 * @module diagram-design/lib/skill
 */

import { readFile } from 'node:fs/promises'
import { join } from 'node:path'

/** Kebab-case identifier the harness addresses this skill by. */
export const SKILL_NAME = 'diagram-design'

/**
 * Provider label.
 *
 * The registry rejects a provider whose candidates claim a different `provider`,
 * and the Cordis plugin that registers it is itself named `diagram-design`, so
 * the two names are kept distinct.
 */
export const PROVIDER_NAME = 'diagram-design-packaged'

/**
 * Precedence rank for this packaged provider. Lower ranks win a duplicate skill
 * name.
 *
 * This deliberately sits **below every local root**, not at the harness's
 * `BUNDLED_SKILL_RANK` of 600. The filesystem provider ranks project-dsh 100,
 * project-agents 200, custom 300, user-dsh 400 and user-agents 500, and this
 * repository's own README tells users to symlink the inner skill into
 * `~/.agents/skills`. At rank 600 that symlink would win, the model would
 * receive the full 29,706-byte `SKILL.md` through the `skill` tool, and DSH's
 * tool-result pruner would middle-elide it at 8,192 characters — silently
 * shipping sections 4 to 11 missing. A host adapter is the supported install,
 * so it must win against a leftover link. Measured on 0.2.0-rc.2: with the
 * symlink present and rank 600, the catalog resolved `provider: "filesystem"`
 * and a 28,661-character body.
 */
export const PLUGIN_SKILL_RANK = 50

/**
 * Hard ceiling for the router body, in characters.
 *
 * Two host facts, both measured rather than assumed, and the second one is the
 * reason this budget exists:
 *
 * 1. `@deepseek-ai/dsh-spill-policy` is mounted in the base bundle with
 *    `maxInlineTokens: 12500`, and prices text at 4 characters per token
 *    (`packages/llm/token-meter/src/estimate.ts`). The rendered `SKILL.md` block
 *    is about 29,000 characters, so it prices at roughly 7,300 tokens, under
 *    that budget — and is therefore delivered **whole** on the turn that loads
 *    the skill. The router is 2,224 characters, about 560 tokens, and the
 *    difference is paid on every load, because a skill body stays in the
 *    request for every later turn.
 * 2. When a session crosses its compaction threshold, `tool-result-pruner`
 *    rewrites `tool/result` events over `thresholdChars: 8192`, keeping
 *    `headChars: 4096` and `tailChars: 1024`. A 29,706-character skill result
 *    is over that line, so it is reduced to its opening and closing, and
 *    sections 4 to 11 leave the history permanently. The router is under the
 *    threshold and is never reduced.
 *
 * The budget is half the threshold rather than all of it, because the rendered
 * content also carries a `<skill_content>` wrapper and a resource hint.
 */
export const ENTRY_BODY_MAX_CHARS = 4096

const FRONTMATTER = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/u

/**
 * Read flat `key: value` pairs out of a YAML frontmatter block.
 *
 * Deliberately not a YAML parser. The only fields this port needs are `name` and
 * `description`, both single-line scalars upstream, and a dependency-free module
 * keeps the plugin free of an npm install. Nested blocks and comments are skipped
 * rather than flattened, so `metadata:` yields no value of its own.
 *
 * @param {string} block - the text between the `---` fences.
 * @returns {Map<string, string>} the flat fields, first occurrence winning.
 */
export function parseFields(block) {
  const fields = new Map()
  for (const line of block.split(/\r?\n/u)) {
    if (/^\s/u.test(line)) continue
    if (line.trimStart().startsWith('#')) continue
    const separator = line.indexOf(':')
    if (separator === -1) continue
    const key = line.slice(0, separator).trim()
    if (key === '' || fields.has(key)) continue
    fields.set(key, unquote(line.slice(separator + 1).trim()))
  }
  return fields
}

/**
 * Strip one layer of matching quotes from a scalar.
 *
 * @param {string} value
 * @returns {string}
 */
function unquote(value) {
  const quote = value[0]
  if ((quote === '"' || quote === "'") && value.length > 1 && value.endsWith(quote)) {
    return value.slice(1, -1)
  }
  return value
}

/**
 * Split a SKILL.md into its routing description and its body.
 *
 * The body is returned so a caller can see what it is choosing not to send. The
 * provider sends `lib/entry.md` instead and leaves this one on disk, reachable
 * through the skill's resource base.
 *
 * @param {string} raw - the complete file contents.
 * @param {string} path - the file path, used in error messages.
 * @returns {{ description: string, body: string }}
 * @throws {Error} when the file has no frontmatter or no usable description.
 */
export function parseSkill(raw, path) {
  const frontmatter = FRONTMATTER.exec(raw)
  if (frontmatter === null) {
    throw new Error(`diagram-design: ${path} has no YAML frontmatter`)
  }
  const description = parseFields(frontmatter[1]).get('description')
  if (description === undefined || description.length === 0) {
    throw new Error(`diagram-design: ${path} frontmatter requires a non-empty description`)
  }
  return { description, body: raw.slice(frontmatter[0].length).trim() }
}

/**
 * Build the candidate the skill registry accepts.
 *
 * `resourceBase` is the reason the model can find `references/` and `SKILL.md`
 * at all: the registry renders this directory into the skill content and tells
 * the model to resolve relative paths against it.
 *
 * @param {{ skillDirectory: string, description: string }} options
 * @returns {object} a skill candidate.
 */
export function buildCandidate({ skillDirectory, description }) {
  return {
    name: SKILL_NAME,
    description,
    invocation: { modelInvocable: true, userInvocable: true },
    provider: PROVIDER_NAME,
    source: 'bundled',
    rank: PLUGIN_SKILL_RANK,
    resourceBase: { kind: 'directory', path: skillDirectory },
    locator: join(skillDirectory, 'SKILL.md'),
    // The filesystem provider publishes this and the Web UI reads it to show
    // where a skill lives; without it the same skill shows a location when it is
    // linked into `~/.agents/skills` and no location when it comes from here.
    path: join(skillDirectory, 'SKILL.md'),
  }
}

/**
 * Read the router body, refusing one the host would reduce.
 *
 * @param {URL | string} url
 * @param {AbortSignal} [signal]
 * @returns {Promise<string>}
 */
export async function loadEntryBody(url, signal) {
  const body = (await readFile(url, { encoding: 'utf8', signal })).trim()
  if (body.length > ENTRY_BODY_MAX_CHARS) {
    throw new Error(`diagram-design: entry body is ${body.length} characters, limit is ${ENTRY_BODY_MAX_CHARS}`)
  }
  return body
}
