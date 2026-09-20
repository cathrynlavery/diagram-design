#!/usr/bin/env python3
"""Generate a Diagram Design diagram with a local LM Studio model, offline.

    python local-agent/agent.py "Flowchart: should I write a skill or a one-off script?"
    python local-agent/agent.py --type architecture --variant dark --size slide-16x9 \\
        --out out/pipeline.html "Architecture of an ETL pipeline: sources, queue, workers, warehouse"
    python local-agent/agent.py --prompt-file brief.md --model qwen/qwen3.8-27b

The loop mirrors what a hosted agent does with the skill, minus the network:

  plan    one small call picks the visual type, variant, size preset, title,
          slug and the ≤9 nodes it will draw (skipped when --type is given
          together with --title)
  draw    one call with the skill's own rules, type reference, template and
          example in context returns the complete HTML file
  verify  self_check.py + verify-geometry.py + structural checks
  repair  findings go back to the model, up to --max-repairs times
  finish  vendored fonts are embedded, the .html is written, then .svg and
          .png are exported next to it

Nothing is fetched at run time. Fonts and Chromium come from
`bootstrap.py`, run once while online.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import export  # noqa: E402
import fonts  # noqa: E402
import prompt  # noqa: E402
import verify  # noqa: E402
from lmstudio import LMStudio, LMStudioError, progress_printer  # noqa: E402

JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
DEFAULT_OUT_DIR = Path("diagrams")


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def parse_plan(reply: str) -> dict:
    match = JSON_RE.search(reply)
    if not match:
        raise ValueError("planning reply contained no JSON object")
    plan = json.loads(match.group(0))
    if not isinstance(plan, dict):
        raise ValueError("planning reply is not a JSON object")
    return plan


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")
    return slug[:60] or "diagram"


def choose_profile(client: LMStudio, model: str, requested: str) -> str:
    if requested != "auto":
        return requested
    info = client.model_info(model) or {}
    loaded = info.get("loaded_context_length") or info.get("max_context_length")
    if loaded and int(loaded) < 48_000:
        log(f"context window is {loaded} tokens → lean prompt profile (use --profile full to override)")
        return "lean"
    return "full"


def run(args: argparse.Namespace) -> int:
    if not fonts.load_manifest():
        log("FAIL fonts are not vendored yet; run `python local-agent/bootstrap.py` once while online")
        return 1
    request = args.prompt_file.read_text(encoding="utf-8") if args.prompt_file else args.request
    if not request or not request.strip():
        log("FAIL give a request as an argument or with --prompt-file")
        return 1

    client = LMStudio(base_url=args.base_url, model=args.model, timeout=args.timeout)
    try:
        model = client.resolve_model()
    except LMStudioError as exc:
        log(f"FAIL {exc}")
        return 1
    log(f"model: {model}")
    profile = choose_profile(client, model, args.profile)

    # -- plan ----------------------------------------------------------------
    plan: dict = {}
    if args.type and args.title:
        plan = {"type": args.type, "title": args.title}
    else:
        started = time.time()
        try:
            reply = client.chat(
                prompt.plan_prompt(request),
                temperature=args.temperature,
                max_tokens=2048,
                on_token=progress_printer("plan "),
            )
            plan = parse_plan(reply)
        except (LMStudioError, ValueError, json.JSONDecodeError) as exc:
            log(f"\nFAIL planning step: {exc}")
            return 1
        log(f" {time.time() - started:.0f}s")
    type_slug = args.type or str(plan.get("type", "")).strip()
    if type_slug not in prompt.available_types():
        log(f"FAIL the plan chose an unknown visual type {type_slug!r}; pass --type explicitly")
        return 1
    variant = args.variant or (plan.get("variant") if plan.get("variant") in prompt.VARIANTS else "light")
    size = args.size or (plan.get("size") if plan.get("size") in prompt.SIZE_PRESETS else "doc-inline")
    plan.setdefault("title", args.title or request.strip().splitlines()[0][:60])
    plan.setdefault("slug", slugify(str(plan["title"])))
    log(f"plan: type={type_slug} variant={variant} size={size} title={plan['title']!r}")
    if plan.get("nodes"):
        log(f"      nodes: {', '.join(map(str, plan['nodes']))}")
    if plan.get("cuts"):
        log(f"      cuts: {plan['cuts']}")

    # -- draw + verify + repair ----------------------------------------------
    context = prompt.DrawContext(type_slug, variant, size, profile=profile, style_guide=args.style_guide)
    base = prompt.draw_messages(context, request, plan)
    messages = list(base)
    log(f"prompt: ~{prompt.estimate_tokens(base[0]['content']) + prompt.estimate_tokens(base[1]['content'])} tokens ({profile})")
    expected_box = prompt.SIZE_PRESETS[size][0]

    out_path = args.out or (DEFAULT_OUT_DIR / f"{plan['slug']}.html")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    html = ""
    findings: list[str] = []
    for round_number in range(args.max_repairs + 1):
        label = "draw " if round_number == 0 else f"repair {round_number} "
        started = time.time()
        try:
            reply = client.chat(
                messages,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                on_token=progress_printer(label),
            )
        except LMStudioError as exc:
            log(f"\nFAIL {exc}")
            return 1
        log(f" {time.time() - started:.0f}s")
        candidate = verify.extract_html(reply)
        if candidate is None:
            out_path.with_suffix(f".reply-{round_number}.txt").write_text(reply, encoding="utf-8")
            log("  ! the reply had no complete HTML document (raw reply saved next to the output)")
            if html:
                # Keep the last good file and ask for the same repair again.
                messages = prompt.repair_messages(base, html, findings)
            else:
                messages = prompt.repair_messages(
                    base, reply[:4000], ["the reply did not contain a complete HTML document in a fenced ```html block"]
                )
            continue
        html = candidate
        out_path.write_text(html, encoding="utf-8")
        findings = verify.verify_file(out_path, expected_box, type_slug)
        if not findings:
            break
        log(f"  {len(findings)} finding(s):")
        for finding in findings:
            log(f"    - {finding}")
        if round_number < args.max_repairs:
            messages = prompt.repair_messages(base, html, findings)

    if not html:
        log("FAIL the model never returned an HTML document")
        return 1

    # -- finish ----------------------------------------------------------------
    html = fonts.inline_html_fonts(html)
    out_path.write_text(html, encoding="utf-8")
    final = verify.verify_file(out_path, expected_box, type_slug)
    status = "OK" if not final else f"WRITTEN WITH {len(final)} OPEN FINDING(S)"
    print(f"{status} {out_path}")
    for finding in final:
        print(f"  - {finding}")
    if not args.no_svg:
        print(f"svg: {export.export_svg(out_path)}")
    if not args.no_png:
        try:
            print(f"png: {export.export_png(out_path, scale=args.scale)}")
        except export.ExportError as exc:
            print(f"png: skipped — {exc}")
    return 0 if not final else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("request", nargs="?", help="what to draw, in plain language")
    parser.add_argument("--prompt-file", type=Path, help="read the request from a file instead")
    parser.add_argument("--type", choices=prompt.available_types(), help="visual type (skips type selection)")
    parser.add_argument("--variant", choices=sorted(prompt.VARIANTS), help="light, dark or full (default: planned)")
    parser.add_argument("--size", choices=sorted(prompt.SIZE_PRESETS), help="size preset (default: planned)")
    parser.add_argument("--title", help="page title; with --type this skips the planning call")
    parser.add_argument("--out", type=Path, help="output .html path (default diagrams/<slug>.html)")
    parser.add_argument("--model", help="LM Studio model id (default: first listed)")
    parser.add_argument("--base-url", default="http://localhost:1234/v1")
    parser.add_argument("--profile", choices=("auto", "full", "lean"), default="auto", help="how much of the skill to send")
    parser.add_argument("--style-guide", type=Path, default=prompt.REFERENCES / "style-guide.md", help="a customised style-guide.md")
    parser.add_argument("--max-repairs", type=int, default=2)
    parser.add_argument("--max-tokens", type=int, default=16384)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--timeout", type=int, default=900, help="seconds to wait for a streamed reply")
    parser.add_argument("--scale", type=float, default=2.0, help="PNG device scale factor")
    parser.add_argument("--no-svg", action="store_true")
    parser.add_argument("--no-png", action="store_true")
    args = parser.parse_args()
    if not args.style_guide.is_file():
        parser.error(f"style guide not found: {args.style_guide}")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
