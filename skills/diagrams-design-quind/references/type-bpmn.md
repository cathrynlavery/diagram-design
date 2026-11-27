# BPMN (proceso con piscinas y carriles)

**Sirve para:** procesos de punta a punta con varios responsables y controles: quién hace qué, en qué orden, dónde se aprueba y dónde termina. Aprobaciones, CI/CD, solicitudes, gobierno de datos.

**No es este tipo:** un flujo entre equipos sin eventos, compuertas ni tipos de tarea → **Swimlane** (`type-swimlane.md`). Lógica de decisión de un solo actor → **Flowchart** (`type-flowchart.md`). Lo que ve el cliente frente a lo que oculta el servicio → **Service blueprint** (`type-service-blueprint.md`).

Es un subconjunto de BPMN 2.0 pensado para leerse sin haber estudiado la notación: cada figura dice su tipo con texto, no solo con la forma.

## Elementos

| Elemento | Forma | Tratamiento |
|---|---|---|
| **Piscina** (una organización, un sistema o un repositorio) | Rectángulo `rx=8`, borde `ink` 1px, con cabecera de 24px (`ink @ 0.05`) y el nombre en `eyebrow` | Ocupa todo el ancho |
| **Carril** (quién ejecuta: un rol, no una persona) | Fila de la piscina; columna de nombre de 136px a la izquierda, con el rol en `node-name` 10px y un verbo en `sublabel` («aprueba») | Divisores `ink @ 0.12`; ≥104px de alto |
| **Evento de inicio** | Círculo `r=12`, borde `ink` 1px | Texto debajo, `muted` 8.5px |
| **Fin con éxito** | Círculo `r=12`, borde de 3px en `series-1` (verde) | Texto debajo |
| **Fin sin éxito** (rechazo o corte) | Círculo `r=12`, borde de 3px en `accent` | Texto debajo |
| **Compuerta exclusiva** | Rombo de 40px con una `X`, borde `ink` | La **pregunta** en `node-name` 9px 600 arriba o abajo, sobre máscara |
| **Tarea** | Caja `rx=6`, 152 x 56 | Según el tipo (tabla siguiente) |

Texto vertical no: el nombre del carril va horizontal en su columna.

### Tipos de tarea

Cada tarea dice su tipo con ícono de 12px + etiqueta `eyebrow`, el nombre (verbo en infinitivo + objeto) y una línea `sublabel`. Si es un control, su código va en esa línea (`control AP-2`).

| Tipo | Etiqueta | Ícono (`quind_icon.py`) | Relleno | Borde |
|---|---|---|---|---|
| Humana | `HUMANA` | `user` | `paper` | `ink` |
| Aprobación humana | `APROBACIÓN` | `stamp` | `series-3 @ 0.08` (ámbar) | `series-3` |
| Automática | `AUTOMÁTICA` | `cog` | `link @ 0.06` (turquesa) | `link` |
| Bot o agente | `BOT` | `bot` | `ink @ 0.02` | `muted` punteado `4,3` |

```svg
<rect x="{x}" y="{y}" width="152" height="56" rx="6" fill="{paper}"/>
<rect x="{x}" y="{y}" width="152" height="56" rx="6" fill="{series-3 @ 0.08}" stroke="{series-3}" stroke-width="1"/>
<!-- quind_icon.py svg stamp --x {x+8} --y {y+7} --size 12 --color {series-3} -->
<text x="{x+24}" y="{y+16}" fill="{series-3}" font-size="7" font-weight="500" font-family="{eyebrow}" letter-spacing="0.08em">APROBACIÓN</text>
<text x="{x+8}" y="{y+34}" fill="{ink}" font-size="11" font-weight="600" font-family="{node-name}">Aprobar el cambio</text>
<text x="{x+8}" y="{y+47}" fill="{muted}" font-size="8" font-family="{sublabel}">control AP-2</text>
```

Ámbar y turquesa aquí son tipos de tarea, no acentos: la regla de 1–2 elementos en `accent` sigue en pie, y `accent` queda para el camino principal y el fin sin éxito.

## Flujos

- **El proceso avanza a la derecha**: cada paso con `x` mayor que el anterior. Los cambios de carril suben o bajan en vertical por una columna sin cajas: compruebe que en esa `x` no haya nada en los carriles que atraviesa.
- **Toda compuerta tiene al menos dos salidas, rotuladas «Sí» / «No»** en `node-name` 9px 600 sobre máscara de `paper`, junto al tramo que sale de la compuerta. Deje ≥52px entre la compuerta y la figura siguiente para que la etiqueta quepa.
- **Bucles** (volver a un paso anterior): por debajo de las cajas del carril, con codos ortogonales.
- **Mensajes entre piscinas**: trazo punteado `5,4` en `link`, y en la clave.
- Conectores `muted`; `accent` solo en el camino principal. Las seis reglas de conectores de `primitives-core.md` aplican; las etiquetas «Sí»/«No» van en tipo oración, no en mayúsculas.

## Reglas

- **Un inicio y al menos un fin.** Todo paso tiene salida; toda figura está dentro de un carril.
- **Un carril por responsable**, nombrado por rol. Un carril con un solo paso está bien.
- **Título con la conclusión** en el `h1` («Un cambio llega a producción solo con pruebas en verde y aprobación del comité»); el `<title>` del SVG, corto (≤60 caracteres). En el `eyebrow`, «BPMN · Proceso».
- **Clave de notación siempre**, con solo los tipos usados.
- **Tamaño**: es la excepción a «más de 9 nodos, parta». Hasta 14 figuras y 5 carriles en un lienzo `doc-wide`. Un proceso más largo se parte por piscina o por tramo, con un evento de enlace («continúa en la figura 2») en el corte; en una imagen o un Word, más de ~1.400px de ancho se reduce demasiado.

## Anti-patrones

- Carriles con nombre de persona («Ana») en vez de rol.
- Una tarea a caballo entre dos carriles: elija un responsable.
- Compuertas sin pregunta, o con salidas sin rotular.
- Aprobaciones dibujadas como tareas humanas corrientes: el control deja de verse.
- Flujos que zigzaguean: reordene los pasos para que la lectura sea casi recta.
- Toda la simbología de BPMN 2.0 (eventos intermedios, subprocesos, compuertas paralelas) cuando el lector no la conoce: si hace falta una figura más, agréguela a la clave.

## Ejemplos

- `assets/example-bpmn.html` — una piscina, tres carriles, dos compuertas, claro
