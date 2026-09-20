#!/usr/bin/env python3
"""Assemble LM Studio prompts from the shipped skill files.

Nothing is paraphrased: the model reads the same SKILL.md sections, style
guide, type reference, template and example a hosted agent would load. This
module only decides *which* of those go into the context window, because a
local model's window is small. Two profiles:

* ``full`` — SKILL.md §1, §4–§9, §12, the style guide, the type reference,
  the variant template and the matching example (~25k tokens).
* ``lean`` — drops the style guide and §8, keeping the rules the linters
  enforce (~15k tokens). Chosen automatically under a 48k context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skills" / "diagram-design"
SKILL_MD = SKILL_DIR / "SKILL.md"
REFERENCES = SKILL_DIR / "references"
ASSETS = SKILL_DIR / "assets"

VARIANTS = {
    "light": ("template.html", ""),
    "dark": ("template-dark.html", "-dark"),
    "full": ("template-full.html", "-full"),
}

# From references/output-spec.md §2. The type ramp is what the model must
# apply; the viewBox is what it must draw into.
SIZE_PRESETS: dict[str, tuple[str, str]] = {
    "doc-inline": ("0 0 960 600", "standard"),
    "doc-wide": ("0 0 1280 720", "standard"),
    "slide-16x9": ("0 0 1280 720", "presentation"),
    "slide-4x3": ("0 0 1024 768", "presentation"),
    "social-og": ("0 0 1200 632", "presentation"),
    "social-square": ("0 0 1080 1080", "presentation"),
    "print-a4-landscape": ("0 0 1120 792", "print"),
    "print-letter-landscape": ("0 0 1056 816", "print"),
}
TYPE_RAMP = {
    "standard": "title 28 · node name 12 (Geist 600) · sublabel 9 · arrow label 8 · eyebrow 8 · node min height 48 · min gap 24",
    "presentation": "title 40 · node name 16 (Geist 600) · sublabel 12 · arrow label 12 · eyebrow 8 · node min height 64 · min gap 40",
    "print": "title 32 · node name 12 (Geist 600) · sublabel 9 · arrow label 8 · eyebrow 8 · node min height 48 · min gap 24",
}

SECTION_RE = re.compile(r"^## (\d+)\. ", re.MULTILINE)
FULL_SECTIONS = ("1", "4", "5", "6", "7", "8", "9", "12")
LEAN_SECTIONS = ("1", "4", "5", "6", "7", "9", "12")


def estimate_tokens(text: str) -> int:
    # Prose and markup both land near 3.6 characters per token for these models.
    return int(len(text) / 3.6)


def available_types() -> list[str]:
    return sorted(path.stem[len("type-") :] for path in REFERENCES.glob("type-*.md"))


def skill_sections() -> dict[str, str]:
    """Map SKILL.md `## N.` section numbers to their full text."""
    source = SKILL_MD.read_text(encoding="utf-8")
    matches = list(SECTION_RE.finditer(source))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        sections[match.group(1)] = source[match.start() : end].rstrip()
    return sections


def visual_type_guide() -> str:
    """The §3 selection table, used by the planning call only."""
    section = skill_sections()["3"]
    start = section.find("### Visual-type guide")
    end = section.find("### Confirm before drawing")
    return section[start:end].strip() if start >= 0 else section


def example_for(type_slug: str, variant: str) -> Path | None:
    suffix = VARIANTS[variant][1]
    reference = REFERENCES / f"type-{type_slug}.md"
    candidates: list[str] = []
    if reference.is_file():
        for name in re.findall(r"assets/(example-[\w-]+\.html)", reference.read_text(encoding="utf-8")):
            if suffix:
                wanted = name.endswith(f"{suffix}.html")
            else:
                wanted = not re.search(r"-(dark|full|terminal)\.html$", name)
            if wanted:
                candidates.append(name)
    candidates.append(f"example-{type_slug}{suffix}.html")
    candidates.append(f"example-{type_slug}.html")
    for name in candidates:
        path = ASSETS / name
        if path.is_file():
            return path
    return None


@dataclass
class DrawContext:
    type_slug: str
    variant: str = "light"
    size: str = "doc-inline"
    profile: str = "full"
    style_guide: Path = REFERENCES / "style-guide.md"
    parts: list[tuple[str, str]] = field(default_factory=list)

    def build(self) -> str:
        if self.type_slug not in available_types():
            raise ValueError(f"unknown visual type {self.type_slug!r}; choose one of {', '.join(available_types())}")
        if self.variant not in VARIANTS:
            raise ValueError(f"unknown variant {self.variant!r}; choose light, dark or full")
        if self.size not in SIZE_PRESETS:
            raise ValueError(f"unknown size {self.size!r}; choose one of {', '.join(SIZE_PRESETS)}")
        sections = skill_sections()
        wanted = FULL_SECTIONS if self.profile == "full" else LEAN_SECTIONS
        self.parts = [("SKILL.md (design rules)", "\n\n".join(sections[key] for key in wanted if key in sections))]
        if self.profile == "full":
            self.parts.append(("references/style-guide.md", self.style_guide.read_text(encoding="utf-8")))
        elif self.style_guide != REFERENCES / "style-guide.md":
            self.parts.append(("references/style-guide.md (custom tokens)", self.style_guide.read_text(encoding="utf-8")))
        self.parts.append((f"references/type-{self.type_slug}.md", (REFERENCES / f"type-{self.type_slug}.md").read_text(encoding="utf-8")))
        template = ASSETS / VARIANTS[self.variant][0]
        self.parts.append((f"assets/{template.name} (start from this file)", template.read_text(encoding="utf-8")))
        example = example_for(self.type_slug, self.variant)
        if example:
            self.parts.append((f"assets/{example.name} (a finished diagram of this type — match its craft, not its content)", example.read_text(encoding="utf-8")))
        return "\n\n".join(f"<<<FILE {name}>>>\n{body}\n<<<END {name.split(' ')[0]}>>>" for name, body in self.parts)

    def system_prompt(self) -> str:
        view_box, ramp = SIZE_PRESETS[self.size]
        return (
            "You are Diagram Design, an editorial diagram author. You write one complete, "
            "self-contained HTML file with an inline SVG diagram, following the design system "
            "below exactly.\n\n"
            "OUTPUT CONTRACT\n"
            "- Reply with exactly one fenced code block tagged `html` containing the whole file, "
            "from `<!DOCTYPE html>` to `</html>`. No prose before or after it.\n"
            "- Start from the template file given below and keep its <head>, CSS and font <link> intact. "
            "Replace only the eyebrow, the <h1>, and the <svg> body.\n"
            f"- Visual type: {self.type_slug}. Variant: {self.variant}. Size preset: {self.size} → "
            f"`viewBox=\"{view_box}\"` plus ~60px extra height if a legend strip is needed. "
            f"Type ramp ({ramp}): {TYPE_RAMP[ramp]}.\n"
            "- Replace every `[diagram-slug]` with a short kebab-case slug for this diagram; keep the "
            "`<title id=\"<slug>-title\">` and `<desc id=\"<slug>-desc\">` as the first children of <svg>, "
            "and `aria-labelledby` naming both ids.\n"
            "- Static output: no <script>, no external images, no CSS @import or url().\n"
            "- Draw arrows before boxes. Every connector between off-axis nodes is a rounded right-angle "
            "elbow, never a diagonal line. Every arrow label sits on an opaque mask rect that keeps a 6–10px "
            "gap from the stroke and never overlaps a node drawn after it.\n"
            "- Use the accent color on at most two elements. Stay within the type's complexity budget; "
            "cut rather than crowd.\n\n"
            "REFERENCE FILES\n"
            + self.build()
        )


def plan_prompt(request: str) -> list[dict]:
    types = ", ".join(available_types())
    sizes = ", ".join(SIZE_PRESETS)
    system = (
        "You are the planning step of Diagram Design. Read the request and choose the layout "
        "using the visual-type guide below. Reply with one JSON object and nothing else, with keys: "
        f"\"type\" (one of: {types}), \"variant\" (light|dark|full), \"size\" (one of: {sizes}), "
        "\"title\" (≤60 chars, the page h1), \"slug\" (kebab-case), \"eyebrow\" (short mono label), "
        "\"desc\" (one sentence saying what the diagram shows, content not geometry), "
        "\"nodes\" (list of the ≤9 node names you will draw), \"cuts\" (what you leave out and why).\n\n"
        + visual_type_guide()
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": request}]


def draw_messages(context: DrawContext, request: str, plan: dict | None) -> list[dict]:
    user = f"REQUEST\n{request.strip()}\n"
    if plan:
        user += (
            "\nPLAN (already agreed — follow it)\n"
            f"- title: {plan.get('title', '')}\n"
            f"- slug: {plan.get('slug', '')}\n"
            f"- eyebrow: {plan.get('eyebrow', '')}\n"
            f"- desc: {plan.get('desc', '')}\n"
            f"- nodes: {', '.join(plan.get('nodes', []) or [])}\n"
            f"- cuts: {plan.get('cuts', '')}\n"
        )
    user += "\nProduce the complete HTML file now."
    return [{"role": "system", "content": context.system_prompt()}, {"role": "user", "content": user}]


def repair_messages(base: list[dict], html: str, findings: list[str]) -> list[dict]:
    """System + request, the latest file, and what is wrong with it.

    Earlier rounds are deliberately dropped: with a 32k window, the rules plus
    two full HTML replies already overflow it, and a truncated context is
    what makes a model return prose instead of a file.
    """
    feedback = (
        "The file you produced failed these automated checks:\n"
        + "\n".join(f"- {finding}" for finding in findings)
        + "\n\nFix every item and return the complete corrected HTML file in one fenced `html` block. "
        "Change nothing that was not flagged."
    )
    return base[:2] + [
        {"role": "assistant", "content": f"```html\n{html}\n```"},
        {"role": "user", "content": feedback},
    ]
