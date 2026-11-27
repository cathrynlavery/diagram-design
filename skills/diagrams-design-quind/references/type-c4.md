# C4 (arquitectura de software)

**Sirve para:** explicar un sistema de software por niveles con el modelo C4 de Simon Brown: contexto, contenedores, componentes, despliegue, dinámico y panorama de sistemas.

**No es este tipo:** un mapa de infraestructura o de integración sin niveles → **Architecture** (`type-architecture.md`). Mensajes ordenados en el tiempo con líneas de vida → **Sequence** (`type-sequence.md`). Zonas, hosts y réplicas sin el modelo C4 detrás → **Deployment** (`type-deployment.md`).

**La prueba de fondo: el diagrama se entiende solo.** Antes de dibujar, responda en una línea qué pregunta contesta y para quién.

## Qué vista hacer

| Vista | Pregunta que responde | Audiencia | Cuándo |
|---|---|---|---|
| **Contexto** (nivel 1) | ¿Qué construimos, quién lo usa, con qué se integra? | Cualquiera | Siempre |
| **Contenedores** (nivel 2) | ¿Qué piezas lo forman, con qué tecnología, cómo se comunican? | Técnica y operación | Siempre |
| **Componentes** (nivel 3) | ¿Cómo se descompone UN contenedor? | Equipo de desarrollo | Solo si aporta; no para almacenes ni servicios triviales |
| **Despliegue** | ¿Dónde corre cada contenedor en este ambiente? | Técnica y operación | Uno por ambiente; con íconos de nube |
| **Dinámico** | ¿Cómo colaboran las piezas en este escenario? | Según el nivel | Con moderación: escenarios complejos o poco evidentes |
| **Panorama** | ¿Cómo encajan varios sistemas de la organización? | Cualquiera | Si se responde por varios sistemas |

**Se dibuja solo lo que se pide.** Si piden «el diagrama de despliegue», sale ese y nada más. Si piden «un diagrama de arquitectura» sin nivel, haga **uno**: contenedores (o contexto si la audiencia no es técnica) y mencione en una línea qué otras vistas podrían sumarse, sin generarlas. El nivel 4 (código) no se dibuja: está en el código.

## Vocabulario

Un **sistema de software** se compone de **contenedores**; un contenedor, de **componentes**. Las **personas** usan los sistemas.

- **Persona**: quien usa el sistema, por rol («Paciente», «Analista de riesgo»). Nunca «Usuario».
- **Sistema de software**: lo que entrega valor a sus usuarios; el que se construye o uno del que depende.
- **Contenedor**: algo que **debe estar corriendo** y **se despliega por separado**: aplicación web, SPA, app móvil, API, proceso batch, función serverless, esquema de base de datos, bucket, cola. No es un contenedor Docker.
- **Componente**: funcionalidad agrupada detrás de una interfaz, dentro del proceso de su contenedor. Debe existir en el código.

| Caso dudoso | Cómo se modela |
|---|---|
| Librería (JAR, DLL, paquete) | No es contenedor; va en la tecnología de quien la usa |
| Dos esquemas en un mismo servidor | Dos contenedores (el servidor aparece en el despliegue) |
| Microservicios propios | Cada servicio es un contenedor y su almacén, otro |
| Microservicios de otro equipo | Sistemas externos: no se ve su interior |
| Datos como servicio (S3, RDS, BigQuery) | Contenedor propio: el bucket o el esquema es del equipo |
| Cola o tema | Cada uno es un contenedor de datos, o va nombrado en la línea con trazo punteado. Nunca «el bus» como una caja al centro |
| Componente compartido (logging) | Dentro de cada contenedor que lo incluye, o se omite |

## Reglas por vista

- **Contexto**: el sistema al centro, en foco; solo personas y sistemas con relación directa; **sin tecnología ni protocolos**.
- **Contenedores**: las mismas personas y sistemas del contexto; frontera del sistema; sin instancias, réplicas ni clústeres (eso es despliegue).
- **Componentes**: un contenedor por diagrama, con su frontera y lo que lo rodea.
- **Despliegue**: nodos anidables (región, clúster, servicio administrado) como zonas de `type-architecture.md`, y adentro las instancias de los contenedores propios, con réplicas si importan. Los servicios de nube son los **nodos**, con su ícono ([`icons-quind.md`](icons-quind.md)); el ícono acompaña a la pieza propia, no la reemplaza.
- **Dinámico**: los mismos elementos del modelo; relaciones numeradas en orden (`1`, `2`, …; el mismo número = en paralelo) en un círculo de 16px sobre la línea.

## Anatomía de la caja

Cada caja lleva **nombre + tipo + tecnología + una frase de qué hace**. Nunca solo el nombre.

```svg
<!-- Contenedor propio: 200 x 88, máscara de papel y luego la caja -->
<rect x="{x}" y="{y}" width="200" height="88" rx="6" fill="{paper}"/>
<rect x="{x}" y="{y}" width="200" height="88" rx="6" fill="{paper}" stroke="{ink}" stroke-width="1"/>
<!-- tipo: etiqueta rectangular rx=2 -->
<rect x="{x+8}" y="{y+8}" width="{w_tag}" height="12" rx="2" fill="none" stroke="{muted}" stroke-width="0.8"/>
<text x="{x+8+w_tag/2}" y="{y+17}" fill="{muted}" font-size="7" font-weight="500" font-family="{eyebrow}" text-anchor="middle" letter-spacing="0.08em">CONTENEDOR</text>
<!-- ícono opcional, 20px, esquina superior derecha: quind_icon.py svg server --x {x+172} --y {y+8} --size 20 -->
<text x="{x+12}" y="{y+40}" fill="{ink}" font-size="12" font-weight="600" font-family="{node-name}">API de citas</text>
<text x="{x+12}" y="{y+54}" fill="{soft}" font-size="8" font-family="{sublabel}">[Spring Boot · Java]</text>
<text x="{x+12}" y="{y+70}" fill="{muted}" font-size="9" font-family="{node-name}">Valida y registra cada cita</text>
```

La frase cabe en una línea de ~36 caracteres (o dos, con la caja de 100px de alto). Cajas del mismo tamaño: el tamaño se lee como importancia.

| Elemento | Etiqueta de tipo | Tratamiento (`style-guide.md`) | Forma |
|---|---|---|---|
| Sistema o contenedor en foco (uno) | `SISTEMA` / `CONTENEDOR` | `focal` | Caja `rx=6` |
| Contenedor o componente propio | `CONTENEDOR` / `COMPONENTE` | `backend` | Caja `rx=6` |
| Almacén de datos (base, bucket, cola) | `CONTENEDOR · DATOS` | `store` + línea inferior de 3px en `muted` | Caja `rx=6` |
| Sistema externo | `SISTEMA EXTERNO` | `external` | Caja `rx=6`, sin tecnología |
| Persona | `PERSONA` | `input` | Píldora `rx` = alto/2 (200 x 64) con ícono `user` en un círculo |
| Frontera de sistema o contenedor | Texto `eyebrow` en `soft` sobre máscara | Sin relleno, `ink` punteado `6,4`, `rx=8` | Rectángulo que encierra lo propio |
| Nodo de despliegue | Texto `eyebrow` + ícono de nube de 20px | Zona (`ink @ 0.02`, borde `ink @ 0.10` continuo) | Rectángulo anidable |

El color solo complementa lo que ya dicen la etiqueta de tipo y la forma: el diagrama debe leerse en blanco y negro.

## Relaciones

- **Una dirección**: de quien inicia a quien recibe. Petición y respuesta es una sola línea.
- **Texto que dice la intención y termina en preposición**, para leer la frase completa: «API de citas *lee y escribe en* Base de datos de citas». Léala en voz alta. «Usa» no dice nada.
- Entre contenedores, además el **protocolo** entre corchetes: `[JSON/HTTPS]`, `[JDBC]`, `[SQS]`.
- **Punteada `5,4` = asíncrona**, y queda en la clave.

**Excepción a la regla 2 de conectores** (`primitives-core.md`): en C4 la etiqueta no va en mayúsculas ni se limita a 14 caracteres. La intención va en `{node-name}` 9px, tipo oración, hasta ~30 caracteres; el protocolo, debajo, en `{sublabel}` 8px. Lo demás no cambia: máscara opaca de `paper`, 6 a 10px de separación del trazo, al lado de los tramos verticales, nunca sobre la línea. Si el texto no cabe, la línea lleva un número y el texto baja a una lista numerada bajo la clave.

Las otras cinco reglas de conectores (ortogonales, sin solapes, puntos de anclaje repartidos, sin pasar detrás de cajas ajenas, máscara antes que nodo) aplican sin excepción. Colores: `muted` por defecto, `link` para llamadas entre contenedores y a sistemas externos, `accent` solo para la relación principal.

## Disposición

- Personas arriba, el sistema o contenedor en foco al centro, dependencias y sistemas externos abajo. Igual en todas las vistas de un mismo sistema.
- **Título**: en el `eyebrow`, el tipo de vista («C4 · Contenedores»); en el `h1`, el alcance («Plataforma de citas»).
- **Clave de notación siempre**, como franja inferior: solo los tipos de caja y de línea que el diagrama usa, más los íconos de nube con el nombre del servicio.
- Más de 9 elementos: **parta por foco** (un caso de uso, un área), no agrande el lienzo.

## Que refleje la realidad

- **Tecnología explícita.** Si no está decidida, las opciones: «PostgreSQL o MySQL». No invente piezas, tecnologías ni integraciones: lo que no se sabe se pregunta.
- Si la presentación a veces lee directo de la base de datos, esa línea se dibuja.
- En propuestas, lo que aún no existe se dice en la frase de la caja («por construir»).
- Nunca credenciales, llaves, cadenas de conexión ni direcciones internas en un diagrama.

## Anti-patrones

- Lista de compras: logos o tecnologías sueltas sin decir qué hace cada pieza.
- Cajas con solo el nombre, o líneas sin texto.
- Nombres genéricos: «Lógica de negocio», «Servicio», «Backend», «Usuario».
- Niveles mezclados: una app, una base de datos y clases en la misma vista.
- Mecanismo de despliegue como caja: «JAR», «imagen Docker». Se dibuja lo que corre.
- Un diagrama de solo íconos de nube: dice qué servicios se usan, no para qué.
- Generar todas las vistas cuando se pidió una.

## Revisión antes de entregar

1. ¿Tiene título y se entiende qué vista es y cuál es su alcance?
2. ¿Tiene clave de notación?
3. ¿Cada elemento tiene nombre, tipo, una frase de qué hace y, donde aplica, tecnología?
4. ¿Cada flecha dice su intención, coincide con la dirección y, entre contenedores, trae el protocolo?
5. ¿Se entienden todas las siglas, colores, formas, íconos y estilos de línea?

## Ejemplos

- `assets/example-c4.html` — vista de contenedores, claro
