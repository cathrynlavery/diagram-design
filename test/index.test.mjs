/**
 * Wiring tests for the plugin entry point.
 *
 * `lib/` is unit-tested in isolation, which means every test there builds its
 * own paths and none of them would notice `index.js` passing a wrong one. Three
 * mutants survived that gap during review: emptying `inject`, making `apply()`
 * register nothing, and pointing the router at a file that does not exist — all
 * shipped a broken plugin with a green suite.
 */

import assert from 'node:assert/strict'
import { stat } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { test } from 'node:test'

import { apply, inject, name } from '../index.js'

function fakeContext() {
  const providers = []
  const commands = []
  const effects = []
  const warnings = []
  const context = {
    skills: { registerProvider: create => providers.push(create({ invalidate() {}, signal: new AbortController().signal })) },
    commands: { register: definition => commands.push(definition) },
    // The real `ctx.effect` does not run the callback; the disposer is returned.
    // Mirror that shape, and hand the disposer back so a test can tear down.
    effect(_fn, label) { effects.push({ label, dispose: () => {} }) },
    logger: { warn: text => warnings.push(String(text)) },
  }
  return {
    ctx: context,
    providers,
    commands,
    effects,
    warnings,
    dispose: () => effects.splice(0).forEach(entry => entry.dispose()),
  }
}

/** Close whatever `apply()` started, so no watcher outlives the test. */
function applyWithTeardown(t, context) {
  apply(context.ctx)
  t.after(() => {
    for (const entry of context.effects.splice(0)) entry.dispose()
  })
}

test('the plugin declares the two services it consumes', () => {
  assert.equal(name, 'diagram-design')
  assert.deepEqual(inject, ['skills', 'commands'])
})

test('apply registers one skill provider and six commands', (t) => {
  const context = fakeContext()

  applyWithTeardown(t, context)
  const { providers, commands } = context

  assert.equal(providers.length, 1)
  assert.equal(commands.length, 6)
  assert.deepEqual(
    commands.map(command => command.name).sort(),
    ['doctor', 'export-diagram', 'import-drawio', 'import-excalidraw', 'import-mermaid', 'profile'],
  )
})

test('the provider points at files that exist in this package', async (t) => {
  const context = fakeContext()

  applyWithTeardown(t, context)
  const [provider] = context.providers
  const [candidate] = await provider.list()

  const directory = candidate.resourceBase.path
  assert.ok(directory.endsWith('skills/diagram-design/'), `unexpected skill directory: ${directory}`)
  assert.ok((await stat(join(directory, 'SKILL.md'))).isFile(), 'SKILL.md is missing from the packaged skill')
  assert.ok((await stat(join(directory, 'references', 'style-guide.md'))).isFile(), 'the router routes to a missing reference')

  // Mutant: `get()` pointed at a router file that does not exist would throw on
  // every skill load in production while every unit test stayed green.
  const definition = await provider.get(candidate, {})
  assert.ok(definition.content.length > 0, 'the router body is empty')
  assert.ok(definition.content.includes('SKILL.md'), 'the router does not route to SKILL.md')
})

test('a provider that cannot read its skill reports and contributes nothing', async (t) => {
  // The registry treats a throwing `list()` as an incomplete catalog and
  // publishes no skills at all, so one missing packaged file would hide every
  // other skill the user installed.
  const context = fakeContext()
  applyWithTeardown(t, context)
  const provider = context.providers[0]
  provider.list = async () => {
    throw new Error('SKILL.md is missing')
  }

  const { createDiagramProvider } = await import('../lib/provider.js')
  const reported = []
  const resilient = createDiagramProvider({
    skillDirectory: fileURLToPath(new URL('../skills/does-not-exist/', import.meta.url)),
    entryFile: fileURLToPath(new URL('../lib/entry.md', import.meta.url)),
    onError: error => reported.push(String(error)),
  })

  assert.deepEqual(await resilient.list({}), [])
  assert.equal(reported.length, 1, 'the failure must be reported, not swallowed')
  assert.match(reported[0], /cannot read the packaged skill/u)
})

test('the packaged files are watched so an editable install refreshes', (t) => {
  const context = fakeContext()

  applyWithTeardown(t, context)

  const watcher = context.effects.find(entry => entry.label.includes('watcher'))
  assert.ok(watcher !== undefined, 'no watcher effect was registered')
})

test('the packaged plugin is the one under this repository', async (t) => {
  const context = fakeContext()

  applyWithTeardown(t, context)
  const [candidate] = await context.providers[0].list()

  assert.equal(
    candidate.resourceBase.path,
    fileURLToPath(new URL('../skills/diagram-design/', import.meta.url)),
  )
})