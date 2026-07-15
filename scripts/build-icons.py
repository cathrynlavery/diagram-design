"""Fetch and normalize the icon set for the diagram-design skill.

Pulls SVGs from Tabler Icons (MIT), Simple Icons (CC0), log-z/logos (MIT),
and Devicon (MIT), normalizes them to a 24x24 viewBox using `currentColor`
so they inherit ink from context, and emits two artifacts:

  - skills/diagram-design/references/primitive-icons.md  (catalog with snippets)
  - skills/diagram-design/assets/icons.html               (visual gallery)

Run:    python scripts/build-icons.py
Reqs:   stdlib only (urllib, re, pathlib)

Re-run any time the manifest below changes. The generated files are
committed; users of the skill never need to run this script.
"""

from __future__ import annotations

import pathlib
import re
import sys
import urllib.request
import urllib.error

REPO = pathlib.Path(__file__).resolve().parent.parent

MD_OUT = REPO / "skills" / "diagram-design" / "references" / "primitive-icons.md"
HTML_OUT = REPO / "skills" / "diagram-design" / "assets" / "icons.html"
VENDOR_DIR = REPO / "scripts" / "vendor" / "icons"


def vendor_path(slot: str, source: str, source_id: str) -> pathlib.Path:
    """Return the local cache path for a given icon."""
    if source == "tabler":
        return VENDOR_DIR / "tabler" / f"{source_id}.svg"
    if source == "simple":
        return VENDOR_DIR / "simple" / f"{source_id}.svg"
    if source == "logz":
        return VENDOR_DIR / "logz" / f"{source_id}.svg"
    if source.startswith("devicon"):
        variant = source.split(":")[1] if ":" in source else "plain"
        return VENDOR_DIR / "devicon" / f"{source_id}-{variant}.svg"
    # "url" source — key by slot name so the cache is human-readable
    safe = re.sub(r"[^\w\-]", "_", slot)
    return VENDOR_DIR / "url" / f"{safe}.svg"

TABLER_URL = "https://raw.githubusercontent.com/tabler/tabler-icons/main/icons/outline/{name}.svg"
TABLER_URL_FALLBACK = "https://raw.githubusercontent.com/tabler/tabler-icons/main/icons/{name}.svg"
SI_URL = "https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/{slug}.svg"
SI_CDN_URL = "https://cdn.jsdelivr.net/npm/simple-icons/icons/{slug}.svg"
LOGZ_URL = "https://raw.githubusercontent.com/log-z/logos/main/website-logos/{name}.svg"
DEVICON_URL = "https://raw.githubusercontent.com/devicons/devicon/master/icons/{name}/{name}-{variant}.svg"
# For "url" source: source_id is the full URL; blurb should note license


# (slot_name, source, source_id, blurb)
# slot_name = what users call the icon
# source = "tabler" or "simple"
# source_id = upstream filename / slug (no extension)
ICONS: dict[str, list[tuple[str, str, str, str]]] = {
    "Compute": [
        ("laptop",     "tabler", "device-laptop",        "User laptop or workstation."),
        ("phone",      "tabler", "device-mobile",        "Mobile phone or tablet client."),
        ("desktop",    "tabler", "device-desktop",       "Desktop computer."),
        ("server",     "tabler", "server",               "Physical server or VM host."),
        ("container",  "tabler", "package",              "Container image or running instance."),
        ("vm",         "tabler", "cube",                 "Virtual machine."),
    ],
    "People": [
        ("user",       "tabler", "user",                 "End user or single actor."),
        ("users",      "tabler", "users",                "Group / cohort / team."),
        ("admin",      "tabler", "user-shield",          "Privileged user / admin."),
        ("robot",      "tabler", "robot",                "Bot, agent, or automated process."),
    ],
    "Network": [
        ("cloud",         "tabler", "cloud",                  "Cloud provider or boundary."),
        ("internet",      "tabler", "world",                  "Public internet."),
        ("cdn",           "tabler", "world-www",              "CDN or edge cache."),
        ("firewall",      "tabler", "wall",                   "Firewall or perimeter control."),
        ("vpn",           "tabler", "shield-lock",            "VPN or encrypted tunnel."),
        ("load-balancer", "tabler", "arrows-split",           "Load balancer / traffic split."),
        ("gateway",       "tabler", "door-enter",             "API gateway or ingress door."),
        ("dns",           "tabler", "tag",                    "DNS / name resolution."),
    ],
    "Data": [
        ("database", "tabler", "database",         "Relational or document database."),
        ("file",     "tabler", "file",             "Generic file."),
        ("log",      "tabler", "file-text",        "Log file / event stream."),
        ("queue",    "tabler", "stack-2",          "Message queue / FIFO."),
        ("cache",    "tabler", "bolt",             "Cache layer."),
        ("bucket",   "tabler", "bucket",            "Object storage / S3 bucket."),
        ("backup",   "tabler", "device-floppy",    "Backup or snapshot."),
        ("search",   "tabler", "search",           "Search index / query."),
    ],
    "Kubernetes": [
        ("pod",        "tabler", "hexagon",                  "Pod (smallest deployable unit)."),
        ("node",       "tabler", "topology-star",            "Cluster node."),
        ("service",    "tabler", "world-cog",                "K8s service / virtual endpoint."),
        ("deployment", "tabler", "rocket",                   "Deployment rollout."),
        ("ingress",    "tabler", "arrow-right-rhombus",      "Ingress controller / route in."),
        ("volume",     "tabler", "device-sd-card",           "Persistent volume."),
    ],
    "Action": [
        ("api",      "tabler", "braces",            "API surface / endpoint."),
        ("request",  "tabler", "arrow-right",       "Outbound request."),
        ("response", "tabler", "arrow-left",        "Inbound response."),
        ("sync",     "tabler", "refresh",           "Sync / reconcile loop."),
        ("lock",     "tabler", "lock",              "Locked / authenticated."),
        ("key",      "tabler", "key",               "Key / secret."),
        ("alert",    "tabler", "alert-triangle",    "Warning / paged alert."),
    ],
    "DevOps": [
        ("git-branch", "tabler", "git-branch",   "Branch / fork point."),
        ("terminal",   "tabler", "terminal",     "Shell / CLI."),
        ("pipeline",   "tabler", "git-merge",    "CI/CD pipeline."),
        ("bug",        "tabler", "bug",          "Bug / defect."),
        ("monitoring", "tabler", "chart-line",   "Metrics / observability."),
        ("test",       "tabler", "test-pipe",    "Test / experiment."),
    ],
    "Brand": [
        # Stroke-style brand outlines (Tabler) where available — match the rest of the set
        ("docker",     "tabler", "brand-docker",       "Docker engine / image."),
        ("terraform",  "tabler", "brand-terraform",    "Terraform IaC."),
        ("aws",        "tabler", "brand-aws",          "Amazon Web Services."),
        ("azure",      "tabler", "brand-azure",        "Microsoft Azure."),
        ("github",     "tabler", "brand-github",       "GitHub."),
        # Filled silhouettes (Simple Icons) for brands Tabler doesn't ship
        ("kubernetes", "simple", "kubernetes",         "Kubernetes."),
        ("gcp",        "simple", "googlecloud",        "Google Cloud."),
        ("postgres",   "simple", "postgresql",         "PostgreSQL."),
        ("redis",      "logz",   "redis",              "Redis."),
        ("nginx",      "simple", "nginx",              "Nginx."),
        ("gitea",      "simple", "gitea",              "Gitea self-hosted git."),
        ("keycloak",          "simple", "keycloak",                    "Keycloak identity / SSO."),
        ("active-directory",  "tabler", "address-book",               "Active Directory / LDAP identity directory."),
        ("minio",      "simple", "minio",              "MinIO S3-compatible object storage."),
        ("mysql",      "logz",   "mysql",              "MySQL."),
        ("oracle",     "simple", "oracle",             "Oracle Database."),
        ("sqlserver",  "simple", "microsoftsqlserver", "Microsoft SQL Server."),
        ("sqlite",     "simple", "sqlite",             "SQLite embedded database."),
        ("hive",       "simple", "apachehive",         "Apache Hive data warehouse."),
        ("starrocks",  "logz",   "starrocks",          "StarRocks MPP analytical DB."),
    ],
    "Data stack": [
        ("nifi",      "simple", "apachenifi",      "Apache NiFi data flow."),
        ("airflow",   "simple", "apacheairflow",   "Apache Airflow scheduler / DAG runner."),
        ("hop",     "url", "https://hop.apache.org/img/hop-logo.svg",                                                                                    "Apache Hop data orchestration / ETL."),
        ("pentaho", "url", "https://cdn.worldvectorlogo.com/logos/pentaho-2.svg",                                                                          "Pentaho PDI (Kettle) ETL & data integration."),
        ("dagster", "url", "https://cdn.prod.website-files.com/681399f654933b29e12fb8bd/6a04996c4dd28c8ad73bbf3d_Dagster%20Icon.svg", "Dagster data orchestration platform."),
        ("trino",     "simple", "trino",           "Trino distributed SQL query engine."),
        ("superset",  "simple", "apachesuperset",  "Apache Superset BI / dashboards."),
        ("redash",    "simple", "redash",          "Redash open-source BI & dashboards."),
        ("tableau",   "simple", "tableau",         "Tableau data visualization."),
        ("powerbi",   "simple", "powerbi",         "Microsoft Power BI."),
        ("jupyter",   "simple", "jupyter",         "Jupyter / JupyterLab notebooks."),
    ],
    "Language": [
        ("python", "simple", "python", "Python."),
        ("r",      "simple", "r",      "R statistical language."),
        ("sql",    "tabler", "sql",    "SQL / generic relational query."),
    ],
    "Statistical tools": [
        ("spss",    "devicon:plain", "spss",            "IBM SPSS Statistics."),
        ("sas",     "url", "https://www.svgrepo.com/download/374062/sas.svg", "SAS analytics platform."),
        ("stata",   "url", "https://icon.icepanel.io/Technology/svg/Stata.svg", "Stata statistical software."),
        ("rstudio", "devicon:plain", "rstudio",         "RStudio / Posit IDE for R and Python."),
        ("qgis",    "simple",        "qgis",            "QGIS open-source GIS platform."),
    ],
    "File formats": [
        ("excel", "tabler", "file-type-xls",  "Microsoft Excel spreadsheet."),
        ("csv",   "tabler", "file-type-csv",  "Comma-separated values file."),
        ("txt",   "tabler", "file-type-txt",  "Plain text file."),
    ],
}


def fetch(url: str) -> str | None:
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "diagram-design-build/1.0 (https://github.com)"}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8")
    except urllib.error.HTTPError:
        return None
    except urllib.error.URLError as e:
        print(f"  network error for {url}: {e}", file=sys.stderr)
        return None


def fetch_tabler(name: str) -> str | None:
    return fetch(TABLER_URL.format(name=name)) or fetch(TABLER_URL_FALLBACK.format(name=name))


def fetch_simple(slug: str) -> str | None:
    return fetch(SI_URL.format(slug=slug)) or fetch(SI_CDN_URL.format(slug=slug))


def fetch_logz(name: str) -> str | None:
    return fetch(LOGZ_URL.format(name=name))


def fetch_devicon(name: str, variant: str = "plain") -> str | None:
    return fetch(DEVICON_URL.format(name=name, variant=variant))


def fetch_url(url: str) -> str | None:
    return fetch(url)


def normalize_tabler(raw: str) -> str:
    """Extract inner geometry from a Tabler SVG and wrap with our normalized attrs."""
    inner = re.search(r"<svg\b[^>]*>(.*?)</svg>", raw, flags=re.DOTALL | re.IGNORECASE)
    if not inner:
        raise ValueError("no <svg> in Tabler payload")
    body = inner.group(1).strip()
    # Drop tabler-icons class wrapper paths (icon-tabler placeholder path that does nothing)
    body = re.sub(r'<path\s+stroke="none"[^/]*?/>', "", body)
    body = re.sub(r"\s+", " ", body).strip()
    return (
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</svg>'
    )


def normalize_simple(raw: str) -> str:
    """Extract path from a Simple Icons SVG; force fill=currentColor."""
    inner = re.search(r"<svg\b[^>]*>(.*?)</svg>", raw, flags=re.DOTALL | re.IGNORECASE)
    if not inner:
        raise ValueError("no <svg> in Simple Icons payload")
    body = inner.group(1).strip()
    body = re.sub(r"\s+", " ", body).strip()
    return (
        '<svg width="24" height="24" viewBox="0 0 24 24" '
        f'fill="currentColor">{body}</svg>'
    )


def normalize_url(raw: str) -> str:
    """Generic normalizer for directly-fetched SVGs (icepanel, vendor CDNs, etc.).
    Extracts inner paths, rewrites fill/stroke colours to currentColor,
    and preserves the original viewBox.

    Rules applied:
    - White / near-white fills (#fff, #ffffff, white) are kept as-is — they
      act as contrast cutouts in 2-colour logos (e.g. white letter on coloured
      circle).  Every other colour becomes currentColor.
    - inline style="fill:#..." is rewritten to a fill= attribute.
    - Inkscape layer translate() transforms are stripped (canvas offset artefact).
    """
    vb_match = re.search(r'viewBox="([^"]+)"', raw, re.IGNORECASE)
    viewbox = vb_match.group(1) if vb_match else "0 0 128 128"
    inner = re.search(r"<svg\b[^>]*>(.*?)</svg>", raw, flags=re.DOTALL | re.IGNORECASE)
    if not inner:
        raise ValueError("no <svg> in payload")
    body = inner.group(1)
    body = re.sub(r"<style\b[^>]*>.*?</style>", "", body, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r"<title\b[^>]*>.*?</title>", "", body, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r"<defs\b[^>]*>.*?</defs>",  "", body, flags=re.DOTALL | re.IGNORECASE)
    # Strip Inkscape canvas-offset translate transforms from group wrappers
    body = re.sub(r'\btransform="translate\([^"]+\)"', '', body)

    def _rewrite_fill(m: re.Match) -> str:
        """Keep white; turn everything else into currentColor."""
        hex_val = m.group(1).lower().strip()
        if hex_val in ("#fff", "#ffffff", "white", "#fefefe", "#fdfdfd"):
            return 'fill="#fff"'
        return 'fill="currentColor"'

    # Rewrite inline style="fill:#rrggbb" → standalone fill= attribute
    body = re.sub(
        r'style="[^"]*fill:\s*(#[0-9a-fA-F]{3,8}|white)[^"]*"',
        lambda m: _rewrite_fill(re.search(r'(#[0-9a-fA-F]{3,8}|white)', m.group(0))),
        body,
    )
    # Rewrite standalone fill="#rrggbb" attributes
    body = re.sub(
        r'\bfill="(#[0-9a-fA-F]{3,8}|white)"',
        _rewrite_fill,
        body,
    )
    body = re.sub(r'\bstroke="#[0-9a-fA-F]{3,8}"', 'stroke="currentColor"', body)
    body = re.sub(r'\bfill="none"', '', body)
    body = re.sub(r"\s+", " ", body).strip()
    return (
        f'<svg width="24" height="24" viewBox="{viewbox}" '
        f'fill="currentColor">{body}</svg>'
    )


def normalize_devicon(raw: str) -> str:
    """Devicon SVGs have colored fills and a 128x128 or 32x32 viewBox.
    Strip fills/classes and rewrite to 24x24 currentColor."""
    inner = re.search(r"<svg\b[^>]*>(.*?)</svg>", raw, flags=re.DOTALL | re.IGNORECASE)
    if not inner:
        raise ValueError("no <svg> in Devicon payload")
    body = inner.group(1)
    body = re.sub(r"<style\b[^>]*>.*?</style>", "", body, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r"<title\b[^>]*>.*?</title>", "", body, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r'\bfill="#[0-9a-fA-F]{3,8}"', 'fill="currentColor"', body)
    body = re.sub(r'\bstroke="#[0-9a-fA-F]{3,8}"', 'stroke="currentColor"', body)
    body = re.sub(r'\bclass="[^"]*"', 'fill="currentColor"', body)
    body = re.sub(r"\s+", " ", body).strip()
    return (
        '<svg width="24" height="24" viewBox="0 0 128 128" '
        f'fill="currentColor">{body}</svg>'
    )


def normalize_logz(raw: str) -> str:
    """log-z/logos SVGs are 100x100 with embedded <style> + class-based fills.
    Strip the style block and rewrite class refs so the icon inherits currentColor."""
    inner = re.search(r"<svg\b[^>]*>(.*?)</svg>", raw, flags=re.DOTALL | re.IGNORECASE)
    if not inner:
        raise ValueError("no <svg> in log-z payload")
    body = inner.group(1)
    body = re.sub(r"<style\b[^>]*>.*?</style>", "", body, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r'\bclass="st\d+"', 'fill="currentColor"', body)
    body = re.sub(r'\bfill="#[0-9a-fA-F]{3,8}"', 'fill="currentColor"', body)
    body = re.sub(r"\s+", " ", body).strip()
    return (
        '<svg width="24" height="24" viewBox="0 0 100 100" '
        f'fill="currentColor">{body}</svg>'
    )


def build() -> tuple[list[str], list[str]]:
    md_chunks: list[str] = []
    gallery_chunks: list[str] = []
    misses: list[str] = []

    md_chunks.append(
        "# Icons (primitive)\n\n"
        "A monochrome 24×24 icon library for IT/cloud diagrams. Each icon "
        "uses `currentColor` so it inherits ink from its parent SVG and "
        "adapts to the editorial skin or any user-onboarded brand palette.\n\n"
        "## Usage\n\n"
        "Find the icon by name (the `### name` headings below). Copy the "
        "fenced `<svg>` snippet into your diagram. Default size is 24×24; "
        "wrap in `<g transform=\"translate(x,y) scale(s)\">` to position and "
        "resize. Set `color`, `fill`, or `stroke` on the parent group/SVG to "
        "control color.\n\n"
        "Generic icons are stroked (1.5px, hairline, like the rest of the "
        "skill); brand silhouettes are filled. Don't mix the two styles in "
        "the same diagram unnecessarily.\n\n"
    )

    for category, items in ICONS.items():
        md_chunks.append(f"## {category}\n\n")
        gallery_chunks.append(f'<section class="cat"><h2>{category}</h2><div class="grid">')

        for slot, source, source_id, blurb in items:
            vpath = vendor_path(slot, source, source_id)

            if source == "tabler":
                normalize = normalize_tabler
                attribution = f"Tabler Icons / `{source_id}` (MIT)"
            elif source == "simple":
                normalize = normalize_simple
                attribution = f"Simple Icons / `{source_id}` (CC0)"
            elif source == "logz":
                normalize = normalize_logz
                attribution = f"log-z/logos / `{source_id}` (MIT)"
            elif source.startswith("devicon"):
                variant = source.split(":")[1] if ":" in source else "plain"
                normalize = normalize_devicon
                attribution = f"Devicon / `{source_id}-{variant}` (MIT)"
            elif source == "url":
                normalize = normalize_url
                domain = re.sub(r"https?://([^/]+)/.*", r"\1", source_id)
                attribution = f"Direct fetch / `{domain}` — verify license before use"
            else:
                raise ValueError(f"unknown source: {source}")

            if vpath.exists():
                print(f"  local   {source}/{source_id} -> {slot}", file=sys.stderr)
                raw = vpath.read_text(encoding="utf-8")
            else:
                print(f"  fetching {source}/{source_id} -> {slot}", file=sys.stderr)
                if source == "tabler":
                    raw = fetch_tabler(source_id)
                elif source == "simple":
                    raw = fetch_simple(source_id)
                elif source == "logz":
                    raw = fetch_logz(source_id)
                elif source.startswith("devicon"):
                    variant = source.split(":")[1] if ":" in source else "plain"
                    raw = fetch_devicon(source_id, variant)
                elif source == "url":
                    raw = fetch_url(source_id)
                if raw is not None:
                    vpath.parent.mkdir(parents=True, exist_ok=True)
                    vpath.write_text(raw, encoding="utf-8")

            if raw is None:
                misses.append(f"{slot} <- {source}/{source_id}")
                md_chunks.append(
                    f"### {slot}\n_NOT FOUND — please pick a fallback_\n\n"
                )
                gallery_chunks.append(
                    f'<div class="cell missing"><div class="icon">∅</div>'
                    f'<div class="name">{slot}</div></div>'
                )
                continue

            try:
                snippet = normalize(raw)
            except ValueError as e:
                misses.append(f"{slot} <- {source}/{source_id} (parse: {e})")
                continue

            md_chunks.append(
                f"### {slot}\n{blurb}\n\n"
                f"```svg\n{snippet}\n```\n\n"
                f"Source: {attribution}\n\n"
            )
            gallery_chunks.append(
                f'<div class="cell"><div class="icon">{snippet}</div>'
                f'<div class="name">{slot}</div></div>'
            )

        gallery_chunks.append("</div></section>")

    md_chunks.append(
        "---\n\n"
        "## License attribution\n\n"
        "- **Tabler Icons** — MIT — https://github.com/tabler/tabler-icons\n"
        "- **Simple Icons** — CC0 — https://github.com/simple-icons/simple-icons\n"
        "- **Devicon** — MIT — https://github.com/devicons/devicon\n"
        "- **log-z/logos** — MIT — https://github.com/log-z/logos\n\n"
        "All libraries' licenses permit redistribution, including in this "
        "repository's MIT-licensed source. Brand logos retain their "
        "respective trademarks; this set is for documentation and "
        "illustrative use only.\n"
    )

    return md_chunks, gallery_chunks, misses


GALLERY_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Icon library · Diagram Design</title>
  <link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --color-paper:   #f5f5f5;
      --color-paper-2: #ececec;
      --color-ink:     #2d3142;
      --color-muted:   #4f5d75;
      --color-soft:    #7a8399;
      --color-rule:    rgba(45,49,66,0.12);
      --color-accent:  #eb6c36;
      --font-sans:     'Geist', system-ui, sans-serif;
      --font-serif:    'Instrument Serif', serif;
      --font-mono:     'Geist Mono', ui-monospace, monospace;
    }
    body {
      font-family: var(--font-sans);
      background: var(--color-paper);
      color: var(--color-ink);
      min-height: 100vh;
      padding: 3rem 2rem;
    }
    .container { max-width: 1200px; margin: 0 auto; }
    .header { margin-bottom: 2.5rem; }
    .eyebrow {
      font-family: var(--font-mono);
      font-size: 0.66rem;
      font-weight: 500;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: var(--color-muted);
      margin-bottom: 0.75rem;
    }
    h1 {
      font-family: var(--font-serif);
      font-size: clamp(1.75rem, 3vw + 1rem, 2.5rem);
      font-weight: 400;
      letter-spacing: -0.02em;
      line-height: 1.1;
      margin-bottom: 0.5rem;
    }
    .subtitle {
      font-size: 1rem;
      line-height: 1.55;
      color: var(--color-muted);
      max-width: 64ch;
    }
    .cat { margin-top: 2.5rem; }
    .cat h2 {
      font-family: var(--font-serif);
      font-size: 1.25rem;
      font-weight: 400;
      margin-bottom: 1rem;
      padding-bottom: 0.5rem;
      border-bottom: 1px solid var(--color-rule);
      color: var(--color-ink);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(6, 1fr);
      gap: 0.5rem;
    }
    @media (max-width: 980px) { .grid { grid-template-columns: repeat(4, 1fr); } }
    @media (max-width: 600px) { .grid { grid-template-columns: repeat(2, 1fr); } }
    .cell {
      background: #fff;
      border: 1px solid var(--color-rule);
      border-radius: 6px;
      padding: 1rem 0.5rem 0.75rem;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.5rem;
      color: var(--color-ink);
      transition: border-color 0.12s, color 0.12s;
    }
    .cell:hover { border-color: var(--color-accent); color: var(--color-accent); }
    .cell .icon { width: 48px; height: 48px; display: flex; align-items: center; justify-content: center; }
    .cell .icon svg { width: 100%; height: 100%; }
    .cell .name {
      font-family: var(--font-mono);
      font-size: 0.62rem;
      letter-spacing: 0.06em;
      color: var(--color-muted);
      text-align: center;
    }
    .cell.missing { opacity: 0.5; }
    .cell.missing .icon { font-size: 24px; color: var(--color-muted); }
    footer {
      margin-top: 3rem;
      padding-top: 1.5rem;
      border-top: 1px solid var(--color-rule);
      font-family: var(--font-mono);
      font-size: 0.72rem;
      letter-spacing: 0.06em;
      color: var(--color-soft);
    }
    footer a { color: inherit; text-decoration: underline dotted; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <p class="eyebrow">Icons · Diagram Design</p>
      <h1>Icon library</h1>
      <p class="subtitle">A small, monochrome library for IT/cloud illustrations. Stroked icons from <a href="https://tabler.io/icons" style="color:inherit">Tabler Icons</a> (MIT); brand silhouettes from <a href="https://simpleicons.org" style="color:inherit">Simple Icons</a> (CC0). Every icon uses <code>currentColor</code> so it inherits ink from its parent.</p>
    </div>
    {SECTIONS}
    <footer>
      Tabler Icons · MIT · github.com/tabler/tabler-icons &nbsp;·&nbsp; Simple Icons · CC0 · github.com/simple-icons/simple-icons &nbsp;·&nbsp; Devicon · MIT · github.com/devicons/devicon
    </footer>
  </div>
</body>
</html>
"""


def main() -> int:
    print("Building icon library…", file=sys.stderr)
    md_chunks, gallery_chunks, misses = build()

    MD_OUT.parent.mkdir(parents=True, exist_ok=True)
    MD_OUT.write_text("".join(md_chunks), encoding="utf-8")

    HTML_OUT.parent.mkdir(parents=True, exist_ok=True)
    html = GALLERY_TEMPLATE.replace("{SECTIONS}", "\n".join(gallery_chunks))
    HTML_OUT.write_text(html, encoding="utf-8")

    total = sum(len(items) for items in ICONS.values())
    print(f"\nDone. {total - len(misses)}/{total} fetched.", file=sys.stderr)
    print(f"  primitive-icons.md: {MD_OUT}", file=sys.stderr)
    print(f"  icons.html:         {HTML_OUT}", file=sys.stderr)
    if misses:
        print(f"\n  {len(misses)} miss(es) — review and pick fallbacks:", file=sys.stderr)
        for m in misses:
            print(f"    - {m}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
