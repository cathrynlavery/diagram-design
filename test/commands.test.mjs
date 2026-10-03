import assert from 'node:assert/strict'
import { mkdtemp, readFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { fileURLToPath } from 'node:url'
import { test } from 'node:test'

import {
  COMMAND_METADATA_BY_NAME,
  COMMAND_NAMES,
  commandBodies,
  composeSteerText,
  registerCommands,
} from '../lib/commands.js'

const SKILL_DIRECTORY = fileURLToPath(new URL('../skills/diagram-design/', import.meta.url))
const COMMAND_NAME = /^[a-z][a-z0-9_-]*$/u
const EXPECTED_NAMES = ['doctor', 'export-diagram', 'import-drawio', 'import-mermaid', 'import-excalidraw', 'profile']

/**
 * Flat `key: value` pairs from a Claude Code command's YAML frontmatter.
 * Deliberately shallow: only `description` and `argument-hint` are read.
 */
function frontmatterFields(raw) {
  const block = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/u.exec(raw)
  assert.ok(block !== null, 'upstream command has no YAML frontmatter')
  const fields = new Map()
  for (const line of block[1].split(/\r?\n/u)) {
    if (/^\s/u.test(line) || line.trimStart().startsWith('#')) continue
    const separator = line.indexOf(':')
    if (separator === -1) continue
    const key = line.slice(0, separator).trim()
    if (key === '' || fields.has(key)) continue
    fields.set(key, line.slice(separator + 1).trim().replace(/^["']|["']$/gu, ''))
  }
  return fields
}

async function upstreamFields(name) {
  const raw = await readFile(new URL(`../commands/${name}.md`, import.meta.url), 'utf8')
  return frontmatterFields(raw)
}

/** Records what `registerCommands` hands to `ctx.commands.register`. */
function fakeContext() {
  const registered = []
  return {
    registered,
    ctx: { commands: { register(definition) { registered.push(definition); return () => {} } } },
  }
}

/** Records everything a handler steers into an agent. */
function fakeAgent() {
  const steered = []
  return { steered, agent: { steer(message) { steered.push(message) } } }
}

/** Stands in for `@deepseek-ai/dsh-llm`'s `createUserMessage`, which mints an id. */
function fakeMessageFactory(input) {
  return Promise.resolve({ id: 'test-message-id', role: 'user', ...input })
}

function invocation(agent, rawInput) {
  return {
    commandId: 'test-command-id',
    agent,
    rawInput,
    attachments: [],
    signal: new AbortController().signal,
  }
}

test('COMMAND_NAMES holds the six upstream commands in a stable order', () => {
  assert.deepEqual([...COMMAND_NAMES], EXPECTED_NAMES)
})

test('every command name is legal for the DSH command registry', () => {
  for (const name of COMMAND_NAMES) {
    assert.match(name, COMMAND_NAME, `${name} is not a legal command name`)
  }
})

test('composeSteerText carries the body and the arguments', () => {
  const text = composeSteerText({ name: 'profile', body: 'BODY TEXT', rawInput: '  load acme  ' })
  assert.ok(text.includes('BODY TEXT'), 'body missing from the steer text')
  assert.ok(text.includes('/profile'), 'command name missing from the steer text')
  assert.ok(text.includes('load acme'), 'arguments missing from the steer text')
})

test('composeSteerText omits the argument label when the user typed none', () => {
  for (const rawInput of ['', '   ', undefined]) {
    const text = composeSteerText({ name: 'doctor', body: 'BODY TEXT', rawInput })
    assert.ok(text.includes('BODY TEXT'), 'body missing from the steer text')
    assert.ok(!text.includes('User arguments'), `dangling argument label for ${JSON.stringify(rawInput)}`)
  }
})

test('commandBodies substitutes the skill directory into every body', async () => {
  const bodies = await commandBodies({ skillDirectory: SKILL_DIRECTORY })
  assert.deepEqual([...bodies.keys()], EXPECTED_NAMES)
  for (const [name, body] of bodies) {
    assert.ok(!body.includes('{{SKILL_DIR}}'), `${name} kept its placeholder`)
    assert.ok(body.includes(SKILL_DIRECTORY), `${name} does not name the installed skill directory`)
    assert.ok(body.includes('source of truth'), `${name} does not defer to the reference`)
  }
})

test('every reference and script path a body names is packaged with the skill', async () => {
  const bodies = await commandBodies({ skillDirectory: SKILL_DIRECTORY })
  for (const [name, body] of bodies) {
    const paths = [...body.matchAll(/`(references|scripts)\/[A-Za-z0-9._-]+\.(?:md|py)`/g)]
      .map(match => match[0].slice(1, -1))
    assert.ok(paths.length > 0, `${name} names no packaged path`)
    for (const relative of new Set(paths)) {
      await assert.doesNotReject(
        readFile(new URL(relative, `file://${SKILL_DIRECTORY}`), 'utf8'),
        `${name} names ${relative}, which is not packaged with the skill`,
      )
    }
  }
})

test('every description and hint matches the upstream command frontmatter', async () => {
  for (const name of COMMAND_NAMES) {
    const metadata = COMMAND_METADATA_BY_NAME[name]
    assert.ok(metadata.description.length > 0, `${name} has an empty description`)
    assert.ok(metadata.hint.length > 0, `${name} has an empty input hint`)
    const upstream = await upstreamFields(name)
    assert.equal(metadata.description, upstream.get('description'), `${name} description drifted`)
    assert.equal(metadata.hint, upstream.get('argument-hint'), `${name} argument hint drifted`)
  }
})

test('registerCommands registers six valid definitions', () => {
  const { ctx, registered } = fakeContext()
  registerCommands(ctx, { skillDirectory: SKILL_DIRECTORY })
  assert.equal(registered.length, 6)
  for (const definition of registered) {
    assert.match(definition.name, COMMAND_NAME)
    assert.ok(definition.description.length > 0, `${definition.name} has no description`)
    assert.equal(typeof definition.handler, 'function')
    assert.ok(definition.input !== undefined, `${definition.name} declares no input`)
    assert.ok(definition.input.hint.length > 0, `${definition.name} has no input hint`)
    assert.equal(
      definition.recordInput,
      false,
      `${definition.name} records rawInput, duplicating the steered payload in the session log`,
    )
  }
})

test('a handler that cannot reach the agent reports an error, not an unhandled rejection', async () => {
  // The message factory is `@deepseek-ai/dsh-llm`'s `createUserMessage`, loaded
  // dynamically. If that package cannot be resolved on a user's machine, the
  // rejection must surface as a command result rather than escaping into the
  // dispatching UI.
  const { ctx, registered } = fakeContext()
  registerCommands(ctx, {
    skillDirectory: SKILL_DIRECTORY,
    messageFactory: () => Promise.reject(new Error('Cannot find package @deepseek-ai/dsh-llm')),
  })
  const { agent, steered } = fakeAgent()

  const result = await registered[0].handler(invocation(agent, '--json'))

  assert.equal(result.kind, 'error')
  assert.ok(result.text.includes('/doctor'), `error text does not name the command: ${result.text}`)
  assert.ok(
    result.text.includes('dsh-llm'),
    `error text does not carry the underlying cause: ${result.text}`,
  )
  assert.equal(steered.length, 0, 'a failed message build must not steer the agent')
})

test('a handler that throws while steering reports an error', async () => {
  const { ctx, registered } = fakeContext()
  registerCommands(ctx, { skillDirectory: SKILL_DIRECTORY, messageFactory: fakeMessageFactory })
  const agent = {
    steer() {
      throw new Error('cannot read inbox state: its projection registration is not active')
    },
  }

  const result = await registered[0].handler(invocation(agent, ''))

  assert.equal(result.kind, 'error')
  assert.ok(result.text.includes('/doctor'))
})

test('a handler steers the body and its arguments into the agent', async () => {
  const { ctx, registered } = fakeContext()
  registerCommands(ctx, { skillDirectory: SKILL_DIRECTORY, messageFactory: fakeMessageFactory })
  const { agent, steered } = fakeAgent()

  const result = await registered[1].handler(invocation(agent, ' diagram.html --png-only '))

  assert.deepEqual(result, { kind: 'success' })
  assert.equal(steered.length, 1)
  const [message] = steered
  assert.equal(message.role, 'user')
  assert.deepEqual(message.source, { kind: 'plugin', plugin: 'diagram-design' })
  const [block] = message.content
  assert.equal(block.type, 'text')
  assert.ok(block.text.includes('/export-diagram'), 'steered text does not name the command')
  assert.ok(block.text.includes('references/export.md'), 'steered text does not route to the reference')
  assert.ok(block.text.includes(SKILL_DIRECTORY), 'steered text does not carry the skill directory')
  assert.ok(block.text.includes('diagram.html --png-only'), 'steered text does not carry the arguments')
})

test('a handler steers without an argument label when none were typed', async () => {
  const { ctx, registered } = fakeContext()
  registerCommands(ctx, { skillDirectory: SKILL_DIRECTORY, messageFactory: fakeMessageFactory })
  const { agent, steered } = fakeAgent()

  await registered[0].handler(invocation(agent, ''))

  assert.ok(!steered[0].content[0].text.includes('User arguments'))
})

test('a missing command body is reported as an error result, not thrown', async () => {
  const empty = await mkdtemp(`${tmpdir()}/diagram-design-empty-`)
  const { ctx, registered } = fakeContext()
  registerCommands(ctx, {
    skillDirectory: SKILL_DIRECTORY,
    bodiesDirectory: empty,
    messageFactory: fakeMessageFactory,
  })
  const { agent, steered } = fakeAgent()

  const result = await registered[0].handler(invocation(agent, '--json'))

  assert.equal(result.kind, 'error')
  assert.ok(result.text.includes('/doctor'), 'error text does not name the command')
  assert.ok(result.text.includes('doctor.md'), `error text does not name the missing file: ${result.text}`)
  assert.equal(steered.length, 0, 'a failed body load must not steer the agent')
})