# Íconos QUIND (Lucide, AWS, Azure, GCP)

Las librerías de íconos de QUIND viven en `assets/icons/` y se consultan con `scripts/quind_icon.py`. Se embeben en el SVG del diagrama: no dependen de la red.

| Librería | Prefijo | Íconos | Contenido |
|---|---|---|---|
| Lucide | (ninguno) | ~1.470 | Íconos de línea genéricos: `server`, `database`, `user`, `smartphone`. ISC |
| AWS | `aws:` | 822 | Servicios (`aws:lambda`), recursos (`aws:res-…`), grupos (`aws:grupo-vpc`, `aws:region`), categorías (`aws:cat-…`) |
| Azure | `azure:` | 662 | Servicios de Azure, Microsoft Entra (`azure:entra-id`) y Power Platform (`azure:power-automate`) |
| Google Cloud | `gcp:` | 252 | Productos principales (`gcp:bigquery`, `gcp:cloud-run`), clásicos (`gcp:pubsub`, `gcp:dataflow`) y categorías |

El juego corto de [`primitive-icons.md`](primitive-icons.md) (87 íconos con el fragmento ya escrito, incluidos logos monocromos de Kubernetes, Docker, lenguajes y herramientas de datos) sigue disponible; use este catálogo cuando necesite un servicio de nube oficial o un ícono que allí no esté.

## Buscar

Desde el directorio del skill:

```bash
python3 scripts/quind_icon.py search lambda                 # en todas las librerías
python3 scripts/quind_icon.py search "load balanc" --lib aws
grep -i "data factor" assets/icons/catalogo.tsv             # el catálogo completo: clave, nombre, categoría
```

Los nombres están en inglés. Hay alias para los servicios más usados: `aws:s3`, `aws:sqs`, `aws:sns`, `aws:ecs`, `aws:eks`, `aws:elb`, `aws:vpc`, `aws:iam`, `aws:region`, `azure:aks`, `azure:adf`, `azure:sql`, `azure:functions`, `azure:storage`, `azure:databricks`, `azure:synapse`, `azure:openai`, `gcp:gcs`, `gcp:functions`, `gcp:spanner`, `gcp:vertex`. Si la clave no existe, el error sugiere parecidas.

## Embeber

```bash
python3 scripts/quind_icon.py svg aws:lambda --x 48 --y 96 --size 32
python3 scripts/quind_icon.py svg server --x 172 --y 8 --size 20 --color "#0e1920"
```

Imprime un `<svg>` anidado para pegar dentro del SVG del diagrama, ya ubicado con `x`, `y`, `width` y `height` (sin `transform`), con `aria-hidden="true"` y sin peticiones de red.

- **Lucide**: trazo de 1.5px en el color que indique `--color` (un rol de `style-guide.md`: `ink`, `muted`, `accent`…). Tamaños: 12px junto a una etiqueta de tipo, 20px en la esquina de una caja.
- **Nube**: la marca oficial tal como la publica su dueño. El script solo prefija sus `id` y clases internas para que dos íconos en un mismo diagrama no choquen. Tamaños: 24 a 32px en una caja o en la cabecera de un nodo de despliegue; alineados a la cuadrícula de 4px.
- No lea los JSON completos al contexto (pesan ~5 MB): busque y embeba siempre con el script.

## Reglas

1. **El ícono acompaña, no reemplaza.** Un diagrama de solo íconos dice qué servicios se usan, no para qué. Cada caja nombra la pieza propia («API de pedidos») y deja el servicio en la tecnología («Cloud Run»). En despliegue, los servicios son los **nodos** y adentro va lo propio.
2. **Un ícono por servicio real.** El del servicio que de verdad se usa, no uno «parecido». Si no hay ícono, use uno de línea (`server`, `database`) y escriba el servicio en la tecnología.
3. **No mezcle proveedores para decorar.** Aparecen los que la solución usa.
4. **No altere las marcas de nube**: sin recortar, girar, recolorear ni deformar. Son de AWS, Microsoft y Google, y se usan solo para representar sus servicios en diagramas de arquitectura. Sus colores son los únicos fuera de la paleta de `style-guide.md` que un diagrama puede llevar; no cuentan como acento.
5. **Van a la clave de notación** con el nombre del servicio (el que devuelve `search`).
6. **No mezcle estilos sin motivo**: Lucide para lo genérico, la marca oficial para el servicio de nube. Íconos de línea y logos rellenos de `primitive-icons.md` no se combinan en una misma fila de cajas.
