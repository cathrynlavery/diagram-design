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
  return {
    ctx: {
      skills: { registerProvider: create => providers.push(create()) },
      commands: { register: definition => commands.push(definition) },
    },
    providers,
    commands,
  }
}

test('the plugin declares the two services it consumes', () => {
  assert.equal(name, 'diagram-design')
  assert.deepEqual(inject, ['skills', 'commands'])
})

test('apply registers one skill provider and six commands', () => {
  const { ctx, providers, commands } = fakeContext()

  apply(ctx)

  assert.equal(providers.length, 1)
  assert.equal(commands.length, 6)
  assert.deepEqual(
    commands.map(command => command.name).sort(),
    ['doctor', 'export-diagram', 'import-drawio', 'import-excalidraw', 'import-mermaid', 'profile'],
  )
})

test('the provider points at files that exist in this package', async () => {
  const { ctx, providers } = fakeContext()

  apply(ctx)
  const [provider] = providers
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

test('the packaged plugin is the one under this repository', async () => {
  const { ctx, providers } = fakeContext()

  apply(ctx)
  const [candidate] = await providers[0].list()

  assert.equal(
    candidate.resourceBase.path,
    fileURLToPath(new URL('../skills/diagram-design/', import.meta.url)),
  )
})