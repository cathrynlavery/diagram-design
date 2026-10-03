/**
 * DeepSeek Harness commands for Diagram Design.
 *
 * Upstream ships six Claude Code slash commands in `commands/`, each a prompt
 * that says "follow this reference, it is the source of truth". A DSH command
 * handler does not reach the model, so each command here does two things:
 * it registers discovery metadata, and its handler steers the command body
 * into the agent as the next instruction.
 *
 * The bodies in `lib/command-bodies/` preserve the upstream behaviour and the
 * upstream required-behaviour steps. They deliberately do not restate anything
 * from `skills/diagram-design/references/` — those files stay the source of
 * truth, exactly as ADR 0008 requires, so upstream keeps owning them.
 *
 * @module diagram-design/lib/commands
 */
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

/** Plugin name used as the message source on everything this module steers. */
const PLUGIN_NAME = 'diagram-design'

/** Packaged directory holding one command body per registered command. */
const BODIES_DIRECTORY_URL = new URL('./command-bodies/', import.meta.url)

/**
 * Registration metadata, transcribed from the `description` and `argument-hint`
 * frontmatter of each `commands/<name>.md`, verbatim.
 *
 * Transcribed rather than parsed: the bodies are packaged with the plugin, while
 * `commands/` is an upstream Claude Code surface that DSH has no reason to read
 * at runtime. `test/commands.test.mjs` re-parses upstream and fails if either
 * string drifts.
 */
const COMMAND_METADATA = [
  {
    name: 'doctor',
    description: 'Run one-shot environment diagnostics for Diagram Design readiness',
    hint: '[--strict] [--json]',
  },
  {
    name: 'export-diagram',
    description: 'Export a diagram-design HTML file to .svg and .png next to the source',
    hint: '<html-file> [--svg-only|--png-only] [--scale=N] [--output=<path>] [--registry]',
  },
  {
    name: 'import-drawio',
    description: 'Redraw a draw.io file as an editorial diagram at a chosen format, size, and detail level',
    hint: '<drawio-file> [--format=html|svg|png|html+png] [--size=<preset>] [--detail=faithful|balanced|simplified] [--audience=engineer|mixed|executive] [--type=<diagram-type>] [--page=N|NAME|all] [--variant=light|dark|full] [--output=<path>]',
  },
  {
    name: 'import-mermaid',
    description: 'Redraw Mermaid as an editorial diagram at a chosen format, size, and detail level',
    hint: '<mermaid-file> [--format=html|svg|png|html+png] [--size=<preset>] [--detail=faithful|balanced|simplified] [--audience=engineer|mixed|executive] [--type=<diagram-type>] [--diagram=N|all] [--variant=light|dark|full] [--output=<path>]',
  },
  {
    name: 'import-excalidraw',
    description: 'Redraw an Excalidraw board as an editorial diagram at a chosen format, size, and detail level',
    hint: '<excalidraw-file> [--format=html|svg|png|html+png] [--size=<preset>] [--detail=faithful|balanced|simplified] [--audience=engineer|mixed|executive] [--type=<diagram-type>] [--variant=light|dark|full] [--output=<path>]',
  },
  {
    name: 'profile',
    description: 'Save, load, inspect, update, reset, or delete diagram-design client profiles',
    hint: '[list|save|load|show|update|reset|delete] [name]',
  },
]

/**
 * Every registered command name, in registration order.
 *
 * `doctor` leads because it is the command a user reaches for first when a
 * diagram will not render; the three imports stay together because they share
 * one flag vocabulary; `profile` is last because it is the least frequent.
 */
export const COMMAND_NAMES = Object.freeze(COMMAND_METADATA.map(command => command.name))

/** The same metadata as {@link COMMAND_NAMES}, keyed by name. Exported for tests. */
export const COMMAND_METADATA_BY_NAME = Object.freeze(
  Object.fromEntries(COMMAND_METADATA.map(command => [command.name, Object.freeze({ ...command })])),
)

/**
 * Read the packaged command bodies and substitute the skill directory.
 *
 * Each body carries a literal `{{SKILL_DIR}}`, replaced here with the absolute
 * path of the installed skill. The model needs the absolute directory: DSH's
 * `resourceBase` renders the same path into the skill content and tells the
 * model to resolve relative paths against it, and these bodies are steered
 * outside that wrapper.
 *
 * @param {object} options
 * @param {string} options.skillDirectory Absolute path of the installed `skills/diagram-design/`.
 * @param {string|URL} [options.bodiesDirectory] Override the packaged bodies directory. Tests use it to exercise the missing-body path.
 * @returns {Promise<Map<string, string>>} Body text by command name, in registration order.
 */
export async function commandBodies({ skillDirectory, bodiesDirectory = BODIES_DIRECTORY_URL }) {
  if (typeof skillDirectory !== 'string' || skillDirectory.length === 0) {
    throw new TypeError('commandBodies: skillDirectory must be a non-empty string')
  }
  const directory = typeof bodiesDirectory === 'string'
    ? bodiesDirectory
    : fileURLToPath(bodiesDirectory)
  const entries = await Promise.all(
    COMMAND_NAMES.map(async name => {
      const raw = await readFile(join(directory, `${name}.md`), 'utf8')
      return [name, raw.replaceAll('{{SKILL_DIR}}', skillDirectory).trim()]
    }),
  )
  return new Map(entries)
}

/**
 * Compose the text handed to `agent.steer` for one command.
 *
 * The argument label is omitted entirely when the user typed none, rather than
 * emitted empty: a command body that ends in "User arguments:" with nothing
 * after it reads as a truncated instruction.
 *
 * @param {object} options
 * @param {string} options.name Registered command name, without the slash.
 * @param {string} options.body Body text from {@link commandBodies}.
 * @param {string} [options.rawInput] Exact text following the command name.
 * @returns {string}
 */
export function composeSteerText({ name, body, rawInput }) {
  const argumentsText = (rawInput ?? '').trim()
  return [
    `The user ran \`/${name}\` in this session. Carry out the command below.`,
    '',
    body.trim(),
    ...(argumentsText === '' ? [] : ['', `User arguments: ${argumentsText}`]),
  ].join('\n')
}

let createUserMessage = undefined

/**
 * Resolve the platform's user-message constructor.
 *
 * Imported lazily so loading this module never requires the LLM package to be
 * resolvable, and cached so the cost is paid once per process rather than once
 * per invocation. The factory is injectable so tests never need the host.
 *
 * @param {{ content: readonly unknown[], source: { kind: string, plugin: string } }} input
 * @returns {Promise<object>}
 */
async function platformMessage(input) {
  if (createUserMessage === undefined) {
    const module = await import('@deepseek-ai/dsh-llm')
    createUserMessage = module.createUserMessage
  }
  return createUserMessage(input)
}

/**
 * Register the six commands on `ctx.commands`.
 *
 * `ctx.commands.register` already files its own fiber effect and returns the
 * disposer, so this function neither wraps the call nor keeps the disposers:
 * the registration is released when the calling fiber unwinds.
 *
 * @param {object} ctx Cordis context carrying the `commands` service.
 * @param {object} options
 * @param {string} options.skillDirectory Absolute path of the installed `skills/diagram-design/`.
 * @param {string|URL} [options.bodiesDirectory] Override the packaged bodies directory.
 * @param {(input: object) => Promise<object>} [options.messageFactory] User-message constructor. Defaults to `@deepseek-ai/dsh-llm`'s.
 * @returns {void}
 */
export function registerCommands(ctx, { skillDirectory, bodiesDirectory, messageFactory = platformMessage } = {}) {
  let bodiesPromise
  const loadBodies = () => {
    bodiesPromise ??= commandBodies({ skillDirectory, bodiesDirectory })
    return bodiesPromise
  }

  for (const { name, description, hint } of COMMAND_METADATA) {
    ctx.commands.register({
      name,
      description,
      // The steered text carries the arguments into the session, so recording
      // `rawInput` on the `command/run` event as well would duplicate the
      // payload in the log.
      recordInput: false,
      input: { hint },
      async handler(invocation) {
        let body
        try {
          body = (await loadBodies()).get(name)
        } catch (error) {
          return { kind: 'error', text: `diagram-design: /${name} could not load its instructions: ${String(error)}` }
        }
        if (body === undefined) {
          return { kind: 'error', text: `diagram-design: no packaged instructions for /${name}.` }
        }
        const text = composeSteerText({ name, body, rawInput: invocation.rawInput })
        try {
          const message = await messageFactory({
            content: [{ type: 'text', text }],
            source: { kind: 'plugin', plugin: PLUGIN_NAME },
          })
          invocation.agent.steer(message)
        } catch (error) {
          return { kind: 'error', text: `diagram-design: /${name} could not reach the agent: ${String(error)}` }
        }
        return { kind: 'success' }
      },
    })
  }
}