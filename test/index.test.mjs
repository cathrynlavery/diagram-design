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
import { stat, utimes } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { test } from 'node:test'

import { apply, inject, name } from '../index.js'

function fakeContext() {
  const providers = []
  const commands = []
  const effects = []
  const warnings = []
  const invalidations = []
  const context = {
    skills: {
      registerProvider(create) {
        // The real control is `{ signal, invalidate }`; `invalidate` clears the
        // catalog cache. Record the calls so a test can prove the watcher makes
        // them — a no-op control made this fix untestable.
        providers.push(create({
          signal: new AbortController().signal,
          invalidate: () => invalidations.push(Date.now()),
        }))
        return () => {}
      },
    },
    commands: { register: definition => { commands.push(definition); return () => {} } },
    // The real `ctx.effect` runs the callback immediately and keeps the returned
    // disposer. Mirror that, or the code under test never runs at all.
    effect(fn, label) {
      const dispose = fn()
      effects.push({ label, dispose: typeof dispose === 'function' ? dispose : () => {} })
      return dispose
    },
    logger: { warn: text => warnings.push(String(text)) },
  }
  return { ctx: context, providers, commands, effects, warnings, invalidations }
}

/** Close whatever `apply()` started, so no watcher outlives the test. */
function applyWithTeardown(t, context) {
  apply(context.ctx)
  t.after(() => {
    for (const entry of context.effects.splice(0)) entry.dispose()
  })
}

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

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

test('editing a packaged file invalidates the skill catalog', async (t) => {
  // `list()` is cached by the registry and `get()` is not, so an editable
  // install is half-live without this: the body refreshes, the description
  // does not. Mutating this to a no-op must fail here.
  const context = fakeContext()
  applyWithTeardown(t, context)
  assert.equal(context.invalidations.length, 0, 'nothing was invalidated at load')

  const entry = fileURLToPath(new URL('../lib/entry.md', import.meta.url))
  const before = new Date(Date.now() - 60_000)
  await utimes(entry, before, before)

  const deadline = Date.now() + 4000
  while (context.invalidations.length === 0 && Date.now() < deadline) await sleep(25)

  assert.ok(
    context.invalidations.length > 0,
    'touching the router did not invalidate the catalog — the watcher is not wired',
  )
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