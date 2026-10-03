/**
 * Tests for the packaged Diagram Design skill provider.
 *
 * Runs under `node --test` with no harness installed: `lib/skill.js` and
 * `lib/provider.js` import nothing outside `node:*`.
 *
 * These tests read the real packaged skill. That is deliberate — the router
 * claims specific files exist and quotes specific routing tokens, and the only
 * way to keep either honest is to check the tree.
 */

import assert from 'node:assert/strict'
import { stat } from 'node:fs/promises'
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { test } from 'node:test'

import { createDiagramProvider } from '../lib/provider.js'
import {
  BUNDLED_SKILL_RANK,
  ENTRY_BODY_MAX_CHARS,
  PROVIDER_NAME,
  SKILL_NAME,
  buildCandidate,
  loadEntryBody,
  parseFields,
  parseSkill,
} from '../lib/skill.js'

const SKILL_DIRECTORY = fileURLToPath(new URL('../skills/diagram-design/', import.meta.url))
const SKILL_FILE = fileURLToPath(new URL('../skills/diagram-design/SKILL.md', import.meta.url))
const ENTRY_FILE = fileURLToPath(new URL('../lib/entry.md', import.meta.url))
const PACKAGED_PATH = /`(?:references|scripts)\/[A-Za-z0-9._-]+\.(?:md|py)`/g

test('parseFields reads flat keys, keeps colons in values, skips nested and commented lines', () => {
  const fields = parseFields([
    'name: demo',
    '# a comment',
    'description: A thing: with a colon, and a comma',
    'metadata:',
    '  version: "2.6"',
  ].join('\n'))

  assert.equal(fields.get('name'), 'demo')
  assert.equal(fields.get('description'), 'A thing: with a colon, and a comma')
  assert.equal(fields.get('metadata'), '')
  assert.equal(fields.has('version'), false, 'an indented nested key is not a flat field')
})

test('parseSkill separates the description from the body and tolerates CRLF', () => {
  const unix = parseSkill('---\nname: x\ndescription: Does a thing\n---\n\n# Title\n\nBody.\n', 'x')
  assert.equal(unix.description, 'Does a thing')
  assert.equal(unix.body, '# Title\n\nBody.')

  const windows = parseSkill('---\r\nname: x\r\ndescription: Does a thing\r\n---\r\n\r\n# Title\r\n', 'x')
  assert.equal(windows.description, 'Does a thing')
  assert.equal(windows.body, '# Title')
})

test('parseSkill rejects a file with no frontmatter and one with an empty description', () => {
  assert.throws(() => parseSkill('# Title only\n', 'x.md'), /has no YAML frontmatter/)
  assert.throws(
    () => parseSkill('---\nname: x\ndescription:\n---\nbody\n', 'x.md'),
    /requires a non-empty description/,
  )
})

test('the packaged description keeps its routing tokens', async () => {
  const { description } = parseSkill(await readFile(SKILL_FILE, 'utf8'), SKILL_FILE)

  assert.ok(description.length > 400, `description is only ${description.length} characters`)
  // Upstream spells the two import formats as file extensions, not product names:
  // the description carries `.drawio` and `.excalidraw`, never `draw.io` or
  // `Excalidraw`. These are the tokens a request actually has to match.
  for (const token of ['flowchart', 'Gantt', 'org chart', '.drawio', 'Mermaid', '.excalidraw']) {
    assert.ok(description.includes(token), `description lost the routing token ${token}`)
  }
})

test('buildCandidate returns a registry-valid candidate', () => {
  const candidate = buildCandidate({ skillDirectory: '/pkg/skills/diagram-design', description: 'd' })

  assert.equal(candidate.name, SKILL_NAME)
  assert.match(candidate.name, /^[a-z0-9]+(?:-[a-z0-9]+)*$/u)
  assert.equal(candidate.provider, PROVIDER_NAME)
  assert.notEqual(candidate.provider, SKILL_NAME, 'the provider label must differ from the plugin name')
  assert.equal(candidate.source, 'bundled')
  assert.equal(candidate.rank, BUNDLED_SKILL_RANK)
  assert.equal(candidate.rank, 600)
  assert.deepEqual(candidate.invocation, { modelInvocable: true, userInvocable: true })
  assert.deepEqual(candidate.resourceBase, { kind: 'directory', path: '/pkg/skills/diagram-design' })
  assert.equal(candidate.locator, '/pkg/skills/diagram-design/SKILL.md')
})

test('the router body is inside the pruning budget', async () => {
  const body = await loadEntryBody(ENTRY_FILE)

  assert.ok(body.length <= ENTRY_BODY_MAX_CHARS, `entry body is ${body.length} characters`)
  assert.equal(body, (await readFile(ENTRY_FILE, 'utf8')).trim())
})

test('every packaged path the router names exists', async () => {
  const entry = await readFile(ENTRY_FILE, 'utf8')
  const named = [...entry.matchAll(PACKAGED_PATH)].map(match => match[0].slice(1, -1))

  assert.ok(named.length >= 8, `the router names only ${named.length} packaged paths`)
  for (const relative of new Set(named)) {
    await assert.doesNotReject(
      readFile(join(SKILL_DIRECTORY, relative), 'utf8'),
      `the router names ${relative}, which is not packaged`,
    )
  }
  assert.ok((await stat(join(SKILL_DIRECTORY, 'assets'))).isDirectory(), 'the router names assets/')
  assert.ok((await stat(join(SKILL_DIRECTORY, 'SKILL.md'))).isFile(), 'the router names SKILL.md')
})

test('the provider lists one skill and loads the router body', async () => {
  const provider = createDiagramProvider({ skillDirectory: SKILL_DIRECTORY, entryFile: ENTRY_FILE })
  const { description } = parseSkill(await readFile(SKILL_FILE, 'utf8'), SKILL_FILE)

  assert.equal(provider.name, PROVIDER_NAME)

  const candidates = await provider.list()
  assert.equal(candidates.length, 1)
  assert.equal(candidates[0].description, description)
  assert.deepEqual(candidates[0].resourceBase, { kind: 'directory', path: SKILL_DIRECTORY })

  const definition = await provider.get(candidates[0], {})
  assert.equal(definition.name, SKILL_NAME)
  assert.equal(definition.provider, PROVIDER_NAME)
  assert.equal(definition.description, description)
  assert.equal(definition.content, (await readFile(ENTRY_FILE, 'utf8')).trim())
  assert.deepEqual(definition.resourceBase, candidates[0].resourceBase)
  assert.equal('rank' in definition, false, 'a definition carries no rank')
  assert.equal('locator' in definition, false, 'a definition carries no locator')
})