#!/usr/bin/env python3
"""Find and embed QUIND icons: Lucide line icons and official AWS, Azure, and GCP marks.

    python3 scripts/quind_icon.py search lambda
    python3 scripts/quind_icon.py search "api gateway" --lib aws
    python3 scripts/quind_icon.py svg aws:lambda --x 48 --y 96 --size 32
    python3 scripts/quind_icon.py svg server --x 48 --y 96 --size 20 --color "#0e1920"

`search` prints key, service name, and category. `svg` prints one inline
`<svg>` element to paste inside the diagram's SVG: it is positioned with
x/y/width/height (no transform), marked aria-hidden, and makes no network
request. Line icons take `--color` (default currentColor). Cloud marks are
their owners' artwork: they are embedded unchanged, with only their internal
ids and class names prefixed so two icons in one diagram cannot collide.

Keys: `server` (Lucide, no prefix), `aws:lambda`, `azure:app-services`,
`gcp:bigquery`. Libraries live in `assets/icons/`. Standard library only.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"
CLOUD_LIBS = ("aws", "azure", "gcp")

ALIAS = {
    "aws:s3": "aws:simple-storage-service", "aws:sqs": "aws:simple-queue-service",
    "aws:sns": "aws:simple-notification-service", "aws:ses": "aws:simple-email-service",
    "aws:eks": "aws:elastic-kubernetes-service", "aws:ecs": "aws:elastic-container-service",
    "aws:ecr": "aws:elastic-container-registry", "aws:elb": "aws:elastic-load-balancing",
    "aws:alb": "aws:elastic-load-balancing", "aws:ebs": "aws:elastic-block-store",
    "aws:vpc": "aws:virtual-private-cloud", "aws:iam": "aws:identity-and-access-management",
    "aws:kms": "aws:key-management-service", "aws:msk": "aws:managed-streaming-for-apache-kafka",
    "aws:opensearch": "aws:opensearch-service", "aws:kinesis-firehose": "aws:data-firehose",
    "aws:mwaa": "aws:managed-workflows-for-apache-airflow",
    "aws:region": "aws:grupo-region", "aws:nube": "aws:grupo-aws-cloud", "aws:cuenta": "aws:grupo-aws-account",
    "aws:subred-publica": "aws:grupo-public-subnet", "aws:subred-privada": "aws:grupo-private-subnet",
    "aws:grupo-vpc": "aws:grupo-virtual-private-cloud-vpc",
    "azure:aks": "azure:kubernetes-services", "azure:vm": "azure:virtual-machine",
    "azure:vnet": "azure:virtual-networks", "azure:adf": "azure:data-factories",
    "azure:sql": "azure:sql-database", "azure:functions": "azure:function-apps",
    "azure:blob": "azure:storage-accounts", "azure:storage": "azure:storage-accounts",
    "azure:apim": "azure:api-management-services", "azure:key-vault": "azure:key-vaults",
    "azure:cosmos": "azure:azure-cosmos-db", "azure:cosmos-db": "azure:azure-cosmos-db",
    "azure:databricks": "azure:azure-databricks", "azure:synapse": "azure:azure-synapse-analytics",
    "azure:openai": "azure:azure-openai", "azure:service-bus": "azure:azure-service-bus",
    "azure:event-hub": "azure:event-hubs", "azure:app-service": "azure:app-services",
    "azure:grupo-recursos": "azure:resource-groups", "azure:suscripcion": "azure:subscriptions",
    "gcp:gcs": "gcp:cloud-storage", "gcp:functions": "gcp:cloud-functions", "gcp:pub-sub": "gcp:pubsub",
    "gcp:kubernetes-engine": "gcp:gke", "gcp:spanner": "gcp:cloud-spanner", "gcp:vertex": "gcp:vertex-ai",
    "gcp:sql": "gcp:cloud-sql", "gcp:gce": "gcp:compute-engine",
}

_LIBS: dict[str, dict] = {}


def library(name: str) -> dict:
    if name not in _LIBS:
        path = ICON_DIR / f"{name}.json"
        if not path.exists():
            raise SystemExit(f"missing icon library: {path}")
        _LIBS[name] = json.loads(path.read_text(encoding="utf-8"))
    return _LIBS[name]


def search(text: str, lib: str | None = None, limit: int = 14) -> list[tuple[str, str, str]]:
    rows = [
        line.rstrip("\n").split("\t")
        for line in (ICON_DIR / "catalogo.tsv").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows = [r + [""] * (3 - len(r)) for r in rows]
    if lib:
        rows = [r for r in rows if (r[0].startswith(lib + ":") if lib != "lucide" else ":" not in r[0])]
    tokens = [t for t in re.split(r"[\s\-_:]+", text.lower()) if t]
    hits = [r for r in rows if all(t in (r[0] + " " + r[1]).lower() for t in tokens)]
    if not hits:
        close = difflib.get_close_matches(text.lower(), [r[0] for r in rows], n=limit, cutoff=0.5)
        hits = [r for r in rows if r[0] in close]
    hits.sort(key=lambda r: (r[0].split(":")[-1].startswith(("res-", "cat-")), len(r[0])))
    return [(r[0], r[1], r[2]) for r in hits[:limit]]


def resolve(key: str) -> tuple[str, str, dict | str]:
    """Return (library, bare key, entry). Exits with suggestions when unknown."""
    key = ALIAS.get(key, key)
    lib, _, name = key.rpartition(":")
    lib = lib or "lucide"
    if lib != "lucide" and lib not in CLOUD_LIBS:
        raise SystemExit(f"unknown icon library «{lib}»: use lucide (no prefix), aws:, azure:, or gcp:")
    entries = library(lib)
    if name not in entries:
        near = ", ".join(k for k, _, _ in search(name, lib, 6)) or "none"
        raise SystemExit(f"no icon «{key}». Similar: {near}. Try: quind_icon.py search {name}")
    return lib, name, entries[name]


SVG_OPEN_RE = re.compile(r"<svg\b([^>]*)>", re.IGNORECASE | re.DOTALL)
ID_RE = re.compile(r'\bid="([^"]+)"')
CLASS_DEF_RE = re.compile(r"\.([A-Za-z_][\w-]*)(?=[\s,{.:])")


def _scoped(body: str, prefix: str) -> str:
    """Prefix ids and class names so several embedded marks cannot collide."""
    ids = set(ID_RE.findall(body))
    for old in sorted(ids, key=len, reverse=True):
        new = f"{prefix}{old}"
        body = body.replace(f'id="{old}"', f'id="{new}"')
        body = body.replace(f"url(#{old})", f"url(#{new})")
        body = body.replace(f'href="#{old}"', f'href="#{new}"')
    styles = re.findall(r"<style[^>]*>(.*?)</style>", body, re.DOTALL)
    classes = {c for css in styles for c in CLASS_DEF_RE.findall(css)}
    for old in sorted(classes, key=len, reverse=True):
        new = f"{prefix}{old}"
        body = re.sub(rf"(<style[^>]*>.*?</style>)", lambda m: re.sub(rf"\.{re.escape(old)}(?![\w-])", f".{new}", m.group(1)), body, flags=re.DOTALL)
        body = re.sub(rf'class="([^"]*)"', lambda m: 'class="' + " ".join(new if c == old else c for c in m.group(1).split()) + '"', body)
    return body


def inline_svg(key: str, x: float, y: float, size: float, color: str = "currentColor") -> str:
    lib, name, entry = resolve(key)
    place = f'x="{x:g}" y="{y:g}" width="{size:g}" height="{size:g}"'
    if lib == "lucide":
        return (
            f'<svg {place} viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.5" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{entry}</svg>'
        )
    source = re.sub(r"<\?xml[^>]*\?>|<!DOCTYPE[^>]*>|<!--.*?-->", "", entry["s"], flags=re.DOTALL).strip()
    match = SVG_OPEN_RE.search(source)
    if not match:
        raise SystemExit(f"icon «{key}» has no <svg> root")
    attrs = match.group(1)
    view = re.search(r'viewBox="([^"]+)"', attrs)
    if view:
        view_box = view.group(1)
    else:
        w = re.search(r'\bwidth="([\d.]+)', attrs)
        h = re.search(r'\bheight="([\d.]+)', attrs)
        view_box = f"0 0 {w.group(1) if w else 64} {h.group(1) if h else 64}"
    body = source[match.end(): source.rindex("</svg>")]
    body = re.sub(r"<title>.*?</title>|<desc>.*?</desc>", "", body, flags=re.DOTALL)
    body = re.sub(r'\sxmlns:xlink="[^"]*"', "", body).replace("xlink:href", "href")
    prefix = "qi-" + re.sub(r"[^a-z0-9]+", "-", f"{lib}-{name}".lower()) + "-"
    return f'<svg {place} viewBox="{view_box}" aria-hidden="true" data-icon="{lib}:{name}">{_scoped(body, prefix)}</svg>'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    find = sub.add_parser("search", help="find icon keys by name")
    find.add_argument("text")
    find.add_argument("--lib", choices=("lucide",) + CLOUD_LIBS)
    find.add_argument("-n", type=int, default=14)
    emit = sub.add_parser("svg", help="print an inline <svg> for one icon")
    emit.add_argument("key")
    emit.add_argument("--x", type=float, default=0)
    emit.add_argument("--y", type=float, default=0)
    emit.add_argument("--size", type=float, default=24)
    emit.add_argument("--color", default="currentColor")
    args = parser.parse_args()

    if args.command == "search":
        aliases = [k for k in ALIAS if args.text.lower() in k and (not args.lib or k.startswith(args.lib))]
        for key in aliases:
            print(f"{key:44} alias of {ALIAS[key]}")
        hits = search(args.text, args.lib, args.n)
        for key, name, category in hits:
            print(f"{key:44} {name}  ·  {category}")
        if not hits and not aliases:
            print("no results: try another word (cloud service names are in English)")
        return 0
    print(inline_svg(args.key, args.x, args.y, args.size, args.color))
    return 0


if __name__ == "__main__":
    sys.exit(main())
