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

/**
 * Records everything a handler submits to an agent, and whether it used the
 * queueing call. `steer` is deliberately absent: the handler must not use it,
 * because a user command queues for the next turn like any other user input
 * rather than interrupting the turn already running.
 */
function fakeAgent() {
  const submitted = []
  const steered = []
  return {
    submitted,
    steered,
    agent: {
      followup(message) { submitted.push(message) },
      steer(message) { steered.push(message) },
    },
  }
}

/** Stands in for `@deepseek-ai/dsh-llm`'s `createUserMessage`, which mints an id. */
function fakeMessageFactory(input) {
  return Promise.resolve({ id: 'test-message-id', role: 'user', ...input })
}

function invocation(agent, rawInput, signal = new AbortController().signal) {
  return { commandId: 'test-command-id', agent, rawInput, attachments: [], signal }
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
      definition.input.attachments,
      definition.attachments,
      `${definition.name} disagrees with itself about attachments`,
    )
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

test('a handler that throws while submitting reports an error', async () => {
  const { ctx, registered } = fakeContext()
  registerCommands(ctx, { skillDirectory: SKILL_DIRECTORY, messageFactory: fakeMessageFactory })
  const agent = {
    followup() {
      throw new Error('cannot read inbox state: its projection registration is not active')
    },
  }

  const result = await registered[0].handler(invocation(agent, ''))

  assert.equal(result.kind, 'error')
  assert.ok(result.text.includes('/doctor'))
})

test('a handler submits the body and its arguments as the next user turn', async () => {
  const { ctx, registered } = fakeContext()
  registerCommands(ctx, { skillDirectory: SKILL_DIRECTORY, messageFactory: fakeMessageFactory })
  const { agent, steered, submitted } = fakeAgent()

  const result = await registered[1].handler(invocation(agent, ' diagram.html --png-only '))

  assert.equal(result.kind, 'success')
  assert.ok(result.text.length > 0, 'a successful command must acknowledge the user')
  assert.equal(steered.length, 0, 'a user command must not steer into the running turn')
  assert.equal(submitted.length, 1)
  const [message] = submitted
  assert.equal(message.role, 'user')
  // `kind: 'user'` is declared in the host's MessageSourceMap. An invented kind
  // renders as an opaque transcript node labelled with its own string.
  assert.deepEqual(message.source, { kind: 'user' })
  const [block] = message.content
  assert.equal(block.type, 'text')
  assert.ok(block.text.includes('/export-diagram'), 'steered text does not name the command')
  assert.ok(block.text.includes('references/export.md'), 'steered text does not route to the reference')
  assert.ok(block.text.includes(SKILL_DIRECTORY), 'steered text does not carry the skill directory')
  assert.ok(block.text.includes('diagram.html --png-only'), 'steered text does not carry the arguments')
})

test('a handler submits without an argument label when none were typed', async () => {
  const { ctx, registered } = fakeContext()
  registerCommands(ctx, { skillDirectory: SKILL_DIRECTORY, messageFactory: fakeMessageFactory })
  const { agent, submitted } = fakeAgent()

  await registered[0].handler(invocation(agent, ''))

  assert.ok(!submitted[0].content[0].text.includes('User arguments'))
})

test('a cancelled invocation does not submit', async () => {
  const { ctx, registered } = fakeContext()
  registerCommands(ctx, { skillDirectory: SKILL_DIRECTORY, messageFactory: fakeMessageFactory })
  const { agent, submitted } = fakeAgent()
  const controller = new AbortController()
  controller.abort()

  const result = await registered[0].handler(invocation(agent, '', controller.signal))

  assert.equal(result.kind, 'error')
  assert.ok(result.text.includes('cancelled'), result.text)
  assert.equal(submitted.length, 0, 'a cancelled command must not submit to the agent')
})

test('a failed body load is retried, not cached for the process', async () => {
  // `Promise.all` reads all six bodies at once, so one transient read failure
  // must not leave every later invocation returning the same cached error.
  const missing = await mkdtemp(`${tmpdir()}/diagram-design-missing-`)
  const { ctx, registered } = fakeContext()
  const options = {
    skillDirectory: SKILL_DIRECTORY,
    bodiesDirectory: missing,
    messageFactory: fakeMessageFactory,
  }
  registerCommands(ctx, options)
  const { agent } = fakeAgent()

  const first = await registered[0].handler(invocation(agent, ''))
  const second = await registered[0].handler(invocation(agent, ''))

  assert.equal(first.kind, 'error')
  assert.equal(second.kind, 'error', 'the retry must attempt the read again')
  assert.notEqual(first.text, undefined)
})

test('a missing command body is reported as an error result, not thrown', async () => {
  const empty = await mkdtemp(`${tmpdir()}/diagram-design-empty-`)
  const { ctx, registered } = fakeContext()
  registerCommands(ctx, {
    skillDirectory: SKILL_DIRECTORY,
    bodiesDirectory: empty,
    messageFactory: fakeMessageFactory,
  })
  const { agent, steered, submitted } = fakeAgent()

  const result = await registered[0].handler(invocation(agent, '--json'))

  assert.equal(result.kind, 'error')
  assert.ok(result.text.includes('/doctor'), 'error text does not name the command')
  assert.ok(result.text.includes('doctor.md'), `error text does not name the missing file: ${result.text}`)
  assert.equal(steered.length + submitted.length, 0, 'a failed body load must not reach the agent')
})
test('the four file-taking commands accept attachments and two do not', () => {
  const { ctx, registered } = fakeContext()
  registerCommands(ctx, { skillDirectory: SKILL_DIRECTORY })

  const accepts = registered.filter(definition => definition.input.attachments === true).map(d => d.name)
  assert.deepEqual(accepts.sort(), ['export-diagram', 'import-drawio', 'import-excalidraw', 'import-mermaid'])
  for (const definition of registered) {
    const hint = definition.input.hint
    if (definition.input.attachments === true) {
      assert.ok(/<[a-z-]+-file>/.test(hint), `${definition.name} accepts files but its hint names none: ${hint}`)
    } else {
      assert.ok(!/<[a-z-]+-file>/.test(hint), `${definition.name} takes no file but its hint names one: ${hint}`)
    }
  }
})

test('attached files lead the submitted message', async () => {
  // Without `attachments: true` the host refuses the submission before the
  // handler runs, so dragging a .drawio into the composer with /import-drawio
  // would never reach the command.
  const { ctx, registered } = fakeContext()
  registerCommands(ctx, { skillDirectory: SKILL_DIRECTORY, messageFactory: fakeMessageFactory })
  const { agent, submitted } = fakeAgent()
  const call = invocation(agent, '')
  call.attachments = [{ type: 'file', file: { id: 'f1', name: 'graph.drawio' } }]

  const result = await registered.find(d => d.name === 'import-drawio').handler(call)

  assert.equal(result.kind, 'success')
  const [message] = submitted
  assert.equal(message.content[0].type, 'file', 'the attachment must lead the message')
  assert.equal(message.content[message.content.length - 1].type, 'text', 'the body must still be the trailing text')
})

/**
 * Behavioural literals restated in both copies. The DSH bodies deliberately
 * compress the upstream Flags sections to a pointer at the reference ("their
 * values and the size presets are in `references/output-spec.md`"), so this
 * table pins only what the bodies actually restate: defaults the model acts
 * on, edge-case sentinels, extractor names, and thresholds. If upstream
 * changes one, the literal vanishes there and this fails until the body
 * follows; if a body invents one, it fails the other way.
 */
const BEHAVIOUR_LITERALS = {
  'doctor': ['--strict', '--json', 'read-only', 'references/doctor.md'],
  'export-diagram': ['device_scale_factor=2', 'assets/index.html', 'data-block-id', '1, 2, 3'],
  'import-drawio': ['drawio_extract.py', 'doc-inline', '960 600', '9 nodes', '24 nodes', 'balanced', 'mixed', 'light'],
  'import-mermaid': ['mermaid_extract.py', 'doc-inline', '960 600', '9 nodes', '24 nodes', 'untrusted', 'unparsed'],
  'import-excalidraw': ['excalidraw_extract.py', 'doc-inline', '960 600', '9 nodes', '24 nodes', 'freedraw'],
  'profile': ['switch', 'marker', '.diagram-design'],
}

/**
 * Extra DSH required-behaviour steps beyond the upstream count, with the
 * reason. The upstream draw.io command has no untrusted-data step; the DSH
 * body carries one like every other import body, so the upstream count stays
 * the floor and only this declared extra is allowed.
 */
const DOCUMENTED_EXTRA_STEPS = {
  'import-drawio': 1,
}

async function upstreamCommand(name) {
  return readFile(new URL(`../commands/${name}.md`, import.meta.url), 'utf8')
}

async function dshBody(name) {
  return readFile(new URL(`../lib/command-bodies/${name}.md`, import.meta.url), 'utf8')
}

/** Every `--flag` token in the text. Upstream input includes the frontmatter hint. */
function flagNames(text) {
  return new Set([...text.matchAll(/--([a-z][a-z0-9-]*)/gu)].map(match => match[1]))
}

/**
 * Numbered steps under the Required behaviour section. Both spellings occur:
 * upstream `commands/` writes "Required behavior", the DSH bodies "Required
 * behaviour". Asserts the section exists — a missing section is a failure,
 * not a zero.
 */
function requiredStepCount(text) {
  const stripped = text.replace(/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/u, '')
  const section = /^(?:##\s+)?required\s+behavio[u]?r\s*$/im.exec(stripped)
  assert.ok(section !== null, 'no Required behaviour section found')
  const rest = stripped.slice(section.index + section[0].length)
  const nextHeading = /^##\s+/m.exec(rest)
  const body = nextHeading === null ? rest : rest.slice(0, nextHeading.index)
  const steps = body.match(/^\s*\d+[.)]\s+/gmu) ?? []
  assert.ok(steps.length > 0, 'Required behaviour section holds no numbered steps')
  return steps.length
}

test('every flag a DSH body names exists upstream, and vice versa', async () => {
  for (const name of COMMAND_NAMES) {
    const upstream = flagNames(await upstreamCommand(name))
    const body = flagNames(await dshBody(name))
    for (const flag of body) {
      assert.ok(upstream.has(flag), `${name}: body names --${flag}, which upstream does not`)
    }
    for (const flag of upstream) {
      assert.ok(body.has(flag), `${name}: upstream names --${flag}, which the body dropped`)
    }
  }
})

test('every restated behaviour literal survives in both copies', async () => {
  for (const name of COMMAND_NAMES) {
    const upstream = await upstreamCommand(name)
    const body = await dshBody(name)
    for (const literal of BEHAVIOUR_LITERALS[name]) {
      assert.ok(upstream.includes(literal), `${name}: upstream no longer says ${JSON.stringify(literal)}`)
      assert.ok(body.includes(literal), `${name}: body no longer says ${JSON.stringify(literal)}`)
    }
  }
})

test('required-behaviour step counts match, with one documented exception', async () => {
  for (const name of COMMAND_NAMES) {
    const upstream = requiredStepCount(await upstreamCommand(name))
    const body = requiredStepCount(await dshBody(name))
    const allowed = upstream + (DOCUMENTED_EXTRA_STEPS[name] ?? 0)
    assert.equal(body, allowed, `${name}: upstream has ${upstream} required steps, body has ${body}`)
  }
})

test('profile routing bullets match the upstream routing', async () => {
  const bullets = text => {
    const stripped = text.replace(/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/u, '')
    const section = /^(?:##\s+)?routing\s*$/im.exec(stripped)
    assert.ok(section !== null, 'no Routing section found')
    const rest = stripped.slice(section.index + section[0].length)
    const nextHeading = /^(?:##\s+|required\s+behavio[u]?r\s*$)/m.exec(rest)
    const body = nextHeading === null ? rest : rest.slice(0, nextHeading.index)
    return body.match(/^\s*-\s+/gmu) ?? []
  }
  const upstream = bullets(await upstreamCommand('profile'))
  const body = bullets(await dshBody('profile'))
  assert.ok(upstream.length > 0 && body.length > 0, 'routing section holds no bullets')
  assert.equal(body.length, upstream.length, `upstream routes ${upstream.length} ways, body ${body.length}`)
})
