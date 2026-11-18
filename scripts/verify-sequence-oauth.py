#!/usr/bin/env python3
"""Structural + skin-lint verification for sequence combined-fragment work.

Drives the real shipped artifacts (type-sequence.md, oauth examples, lint-skin.py).
Exit 0 only when all gates pass. Intended for local/PR checks alongside:
  python scripts/lint-skin.py --all --baseline
"""

from __future__ import annotations

import math
import re
import subprocess
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TYPE_SEQ = ROOT / "skills/diagram-design/references/type-sequence.md"
ASSETS = ROOT / "skills/diagram-design/assets"
COLD = [
    ASSETS / "example-sequence.html",
    ASSETS / "example-sequence-dark.html",
    ASSETS / "example-sequence-full.html",
]
OAUTH = [
    ASSETS / "example-sequence-oauth.html",
    ASSETS / "example-sequence-oauth-dark.html",
    ASSETS / "example-sequence-oauth-full.html",
]
LINT = ROOT / "scripts/lint-skin.py"

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
NONRENDERING = {"defs", "title", "desc", "metadata", "marker", "pattern", "symbol", "clippath", "mask", "script", "style", "template"}
INHERITED = {"visibility", "fill", "fill-opacity", "font-size", "stroke", "stroke-opacity", "stroke-width", "stroke-dasharray"}
CSS_GEOMETRY = {"transform", "translate", "rotate", "scale", "x", "y", "dx", "dy", "clip-path", "mask", "filter"}
CSS_PAINT = {"fill", "fill-opacity", "stroke", "stroke-opacity", "stroke-width", "stroke-dasharray", "marker-end"}
CSS_SIZE = {"width", "height"}
VISIBILITY_ALPHA = {"opacity", "fill-opacity", "stroke-opacity"}
VISIBILITY_VALUES = VISIBILITY_ALPHA | {"display", "visibility", "content-visibility", "font-size", "fill", "stroke"}


@dataclass(eq=False)
class Element:
    tag: str
    attrs: dict[str, str]
    parent: Element | None = None
    content: list[str | Element] = field(default_factory=list)

    def ancestors(self):
        node = self
        while node is not None:
            yield node
            node = node.parent


class SequenceParser(HTMLParser):
    """Read actual elements, excluding comments and raw style/script markup."""

    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.root = Element("document", {})
        self.stack = [self.root]
        self.elements: list[Element] = []
        self.feed(source)
        self.close()
        self.hide_rules = []
        self.rules = []
        for node in self.elements:
            if node.tag == "style":
                css = re.sub(r"/\*.*?\*/", "", "".join(x for x in node.content if isinstance(x, str)), flags=re.S)
                for selectors, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
                    values = dict(re.findall(r"([\w-]+)\s*:\s*([^;]+)", declarations))
                    selectors = css_parts(selectors, ",")
                    self.rules.extend((selector, values) for selector in selectors)
                    if hides(values, text=True):
                        self.hide_rules.extend((selector, values) for selector in selectors)

    def handle_starttag(self, tag, attrs):
        values = {}
        for key, value in attrs:
            values.setdefault(key, value or "")
        node = Element(tag, values, self.stack[-1])
        self.stack[-1].content.append(node)
        self.elements.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].content.append(data)

    def visible(self, node: Element) -> bool:
        chain = list(node.ancestors())
        text = any(x.tag in {"text", "tspan"} for x in chain)
        if not any(x.tag == "svg" for x in chain):
            return False
        inherited = {}
        for ancestor in reversed(chain):
            values = properties(ancestor)
            inherited.update((key, value) for key, value in values.items() if key in INHERITED)
            if (ancestor.tag in NONRENDERING or "hidden" in ancestor.attrs
                    or hides({key: value for key, value in values.items() if key not in INHERITED})
                    or any(selector_may_match(selector, ancestor) and hides(rule, text=text)
                           for selector, rule in self.hide_rules)):
                return False
        if hides({key: value for key, value in inherited.items() if key in {"visibility", "font-size"}}, text=text):
            return False
        if node.tag in {"line", "rect"} or text:
            stroke = (not transparent(inherited.get("stroke", "none"))
                      and positive(inherited.get("stroke-opacity", "1"))
                      and positive(inherited.get("stroke-width", "1")))
            fill = (not transparent(inherited.get("fill", "black"))
                    and positive(inherited.get("fill-opacity", "1")))
            return stroke if node.tag == "line" else fill or stroke
        return True

    def text(self, node: Element) -> str:
        # A text container can have no own paint while a tspan restores it.
        return "".join((part if self.visible(node) else "") if isinstance(part, str)
                       else self.text(part) for part in node.content)


def properties(node: Element) -> dict[str, str]:
    values = dict(node.attrs)
    inline = re.sub(r"/\*.*?\*/", "", values.get("style", ""), flags=re.S)
    values.update((key.lower(), value) for key, value in re.findall(r"([\w-]+)\s*:\s*([^;]+)", inline))
    return {key: re.sub(r"\s*!important\s*$", "", value, flags=re.I).strip().lower()
            for key, value in values.items()}


def marker(node: Element) -> str:
    value = ""
    for ancestor in reversed(list(node.ancestors())):
        own = properties(ancestor).get("marker-end")
        if own is not None and own not in {"inherit", "unset"}:
            value = "" if own in {"none", "initial"} else own
    return value


def positive(raw: str) -> bool:
    try:
        value = float(raw.removesuffix("%").removesuffix("px"))
        return math.isfinite(value) and value > 0
    except ValueError:
        return False


def transparent(fill: str) -> bool:
    return (fill in {"none", "transparent"}
            or bool(re.fullmatch(r"#(?:[0-9a-f]{6}00|[0-9a-f]{3}0)", fill))
            or bool(re.search(r"(?:rgba|hsla)\([^()]*,\s*0(?:\.0*)?%?\s*\)$", fill))
            or bool(re.search(r"/\s*0(?:\.0*)?%?\s*\)$", fill)))


def unresolved_visibility(values: dict[str, str]) -> list[str]:
    """Refuse visual values this static checker cannot resolve, never guess them."""
    findings = []
    for name, raw in values.items():
        name = name.lower()
        if name not in VISIBILITY_VALUES:
            continue
        value = re.sub(r"\s*!important\s*$", "", raw, flags=re.I).strip().lower()
        unknown = (value in {"inherit", "initial", "unset", "revert", "revert-layer", "currentcolor"}
                   or bool(re.search(r"\b(?:var|env|calc|min|max|clamp)\s*\(", value)))
        if name in VISIBILITY_ALPHA:
            numeric = value.removesuffix("%")
            unknown = (not re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?", numeric)
                       or not math.isfinite(float(numeric)))
        if unknown:
            findings.append(f"unresolved visibility value for {name}: {raw!r}")
    return findings


def hides(values: dict[str, str], text: bool = False) -> bool:
    values = {key.lower(): re.sub(r"\s*!important\s*$", "", value, flags=re.I).strip().lower()
              for key, value in values.items()}
    if values.get("display") == "none" or values.get("visibility") in {"hidden", "collapse"}:
        return True
    if values.get("content-visibility") == "hidden":
        return True
    if text:
        fill = values.get("fill", "")
        if transparent(fill):
            return True
        if re.fullmatch(r"[-+]?(?:0+(?:\.0*)?|\.0+)(?:[a-z]+|%)?", values.get("font-size", "")):
            return True
    for key in (("opacity", "fill-opacity", "font-size") if text else ("opacity",)):
        raw = values.get(key, "").removesuffix("%").removesuffix("px")
        try:
            if raw and float(raw) <= 0:
                return True
        except ValueError:
            pass
    return False


def css_parts(source: str, separators: str) -> list[str]:
    """Split selector lists/compounds outside quoted attributes and functions."""
    parts, start, depth, quote, escaped = [], 0, 0, "", False
    for index, char in enumerate(source):
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif quote:
            if char == quote:
                quote = ""
        elif char in {"'", '"'}:
            quote = char
        elif char in "([":
            depth += 1
        elif char in ")]":
            depth = max(0, depth - 1)
        elif depth == 0 and (char in separators or " " in separators and char.isspace()):
            if source[start:index].strip():
                parts.append(source[start:index].strip())
            start = index + 1
    if source[start:].strip():
        parts.append(source[start:].strip())
    return parts


def selector_may_match(selector: str, node: Element) -> bool:
    """Conservative CSS hiding check, following the architecture verifier.

    This bounded static checker does not implement the CSS cascade: a possible
    hiding rule is refused even if another rule might restore visibility.
    """
    compounds = css_parts(selector, " >+~")
    last = compounds[-1] if compounds else ""
    if not last:
        return True
    tag = re.match(r"^(?:[\w*-]*\|)?([\w-]+|\*)", last)
    escaped_tag = tag is not None and last[tag.end():].startswith("\\")
    if tag and not escaped_tag and tag[1] not in {node.tag, "*"}:
        return False
    if any(char in last for char in (":", "\\", "[")):
        return True
    return (all(value == node.attrs.get("id") for value in re.findall(r"#([\w-]+)", last))
            and set(re.findall(r"\.([\w-]+)", last)) <= set(node.attrs.get("class", "").split()))


def coordinate(node: Element, name: str) -> float:
    value = float(node.attrs.get(name, "nan"))
    if not math.isfinite(value):
        raise ValueError(f"{node.tag} has missing or invalid {name}")
    if name in {"x", "x1", "x2", "y", "y1", "y2"}:
        if node.tag == "text" and name in {"x", "y"}:
            offset = float(node.attrs.get("d" + name, "0"))
            if not math.isfinite(offset):
                raise ValueError("text offsets must be finite")
            value += offset
        for ancestor in node.ancestors():
            raw = ancestor.attrs.get("transform", "").strip()
            if not raw:
                continue
            match = re.fullmatch(r"translate\(\s*([-+\d.eE]+)(?:[\s,]+([-+\d.eE]+))?\s*\)", raw)
            if match is None:
                raise ValueError("OAuth geometry supports translate transforms only")
            offset = float(match[1]) if name.startswith("x") else float(match[2] or "0")
            if not math.isfinite(offset):
                raise ValueError("OAuth translation must be finite")
            value += offset
    return value


def dashed(node: Element) -> bool:
    raw = ""
    for ancestor in reversed(list(node.ancestors())):
        raw = properties(ancestor).get("stroke-dasharray", raw)
    if raw in {"", "none"}:
        return False
    values = []
    for part in re.split(r"[\s,]+", raw.strip()):
        match = re.fullmatch(r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?)(?:px|%)?", part)
        if match is None:
            raise ValueError(f"unsupported stroke-dasharray length {part!r}; use numbers, px or %")
        values.append(float(match[1]))
    if len(values) % 2:
        values *= 2
    return (all(math.isfinite(x) and x >= 0 for x in values)
            and any(x > 0 for x in values[::2]) and any(x > 0 for x in values[1::2]))


def check_oauth(source: str) -> list[str]:
    """Check the shipped OAuth story, not arbitrary sequence diagrams.

    All ordinary returns travel right-to-left in this example. Derive their
    positions and the two ALT regions from the SVG rather than fixed y values.
    The named accent marker is the existing headline-success exception.
    Guard spans must inherit their parent text position; independently positioned
    spans need a renderer and are refused rather than checked at the wrong point.
    """
    document = SequenceParser(source)
    diagrams = [node for node in document.elements if node.tag == "svg" and node.attrs.get("role") == "img"
                and not any(ancestor.tag == "svg" for ancestor in list(node.ancestors())[1:])]
    if len(diagrams) != 1:
        return ['require one top-level OAuth diagram SVG with role="img"']
    scoped = [node for node in document.elements if diagrams[0] in node.ancestors()]
    visible = [node for node in scoped if document.visible(node)]
    texts = [(node, " ".join(document.text(node).split())) for node in scoped if node.tag == "text"]
    texts = [(node, text) for node, text in texts if text]
    lines = [node for node in visible if node.tag == "line"]
    rects = [node for node in visible if node.tag == "rect"]
    errors = []
    # No CSS cascade is implemented for paint or geometry. Refuse matching
    # overrides rather than certify the attributes while CSS changes the marks.
    for node in scoped:
        chain = list(node.ancestors())
        if (node.tag not in {"line", "rect", "text", "tspan"} and not any(x.tag == "text" for x in chain)
                or not any(x.tag == "svg" for x in chain)):
            continue
        if any(x.tag in NONRENDERING for x in node.ancestors()):
            continue
        if sum(ancestor.tag == "svg" for ancestor in chain) > 1:
            errors.append("unsupported nested SVG coordinate system on checked elements")
        for ancestor in node.ancestors():
            errors.extend(unresolved_visibility(properties(ancestor)))
            inline = re.sub(r"/\*.*?\*/", "", ancestor.attrs.get("style", ""), flags=re.S)
            keys = {key.lower() for key, _ in re.findall(r"([\w-]+)\s*:\s*([^;]+)", inline)}
            if keys & CSS_GEOMETRY or any(ancestor.attrs.get(key, "none") != "none" for key in ("clip-path", "mask", "filter")):
                errors.append("unsupported inline SVG geometry or clipping override")
            if ancestor.tag == "rect" and keys & CSS_SIZE:
                errors.append("unsupported inline rectangle size override")
            for selector, values in document.rules:
                if selector_may_match(selector, ancestor):
                    errors.extend(unresolved_visibility(values))
                    rule_keys = {key.lower() for key in values}
                    if rule_keys & (CSS_GEOMETRY | CSS_PAINT):
                        errors.append("unsupported stylesheet override of SVG paint or geometry")
                    if ancestor.tag == "rect" and rule_keys & CSS_SIZE:
                        errors.append("unsupported stylesheet rectangle size override")
    if errors:
        return sorted(set(errors))
    try:
        horizontal = [node for node in lines if coordinate(node, "y1") == coordinate(node, "y2")]
        lifelines = [node for node in lines if coordinate(node, "x1") == coordinate(node, "x2")
                     and coordinate(node, "y1") != coordinate(node, "y2")
                     and not marker(node) and dashed(node)]
        returns = [node for node in horizontal if coordinate(node, "x1") > coordinate(node, "x2")
                   and marker(node) != "url(#arrow-accent)"]
        for node in returns:
            if not dashed(node):
                errors.append(f"ordinary return at y={coordinate(node, 'y1'):g} must be dashed")

        def contains(rect, x, y):
            return (coordinate(rect, "x") <= x <= coordinate(rect, "x") + coordinate(rect, "width")
                    and coordinate(rect, "y") <= y <= coordinate(rect, "y") + coordinate(rect, "height"))

        def positioned_children(node):
            # Even an empty/whitespace span can move the following text cursor.
            return any(any(key in child.attrs for key in ("x", "y", "dx", "dy", "transform"))
                       for child in scoped if node in list(child.ancestors())[1:])

        # Percentage backgrounds are not fragment rectangles.
        rects = [node for node in rects if all(re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", node.attrs.get(key, ""))
                                               for key in ("x", "y", "width", "height"))]
        fragments = []
        for operator, text in texts:
            if text != "ALT":
                continue
            for rect in rects:
                if not contains(rect, coordinate(operator, "x"), coordinate(operator, "y")):
                    continue
                dividers = [line for line in horizontal if not marker(line)
                            and dashed(line)
                            and coordinate(line, "x1") != coordinate(line, "x2")
                            and coordinate(rect, "y") < coordinate(line, "y1") < coordinate(rect, "y") + coordinate(rect, "height")
                            and contains(rect, coordinate(line, "x1"), coordinate(line, "y1"))
                            and contains(rect, coordinate(line, "x2"), coordinate(line, "y2"))]
                if len(dividers) == 1:
                    fragments.append((rect, dividers[0], operator))
        if len(fragments) != 1:
            errors.append("require one visible ALT operator in a two-region fragment with a dashed divider")
        else:
            frame, divider, operator = fragments[0]
            region1 = region2 = False
            for node, text in texts:
                if text.startswith("[") and positioned_children(node):
                    errors.append("guard spans must inherit their parent text position")
                    continue
                if not contains(frame, coordinate(node, "x"), coordinate(node, "y")):
                    continue
                y = coordinate(node, "y")
                region1 |= text == "[token valid]" and coordinate(operator, "y") < y < coordinate(divider, "y1")
                region2 |= bool(re.fullmatch(r"\[else(?:\s.*)?\]", text)) and coordinate(divider, "y1") < y
            if not region1:
                errors.append("missing visible [token valid] guard in the first ALT region")
            if not region2:
                errors.append("missing visible else-region guard in the second ALT region")

            # Bind the required responses to their visible labels inside the
            # failure region. Legend samples cannot stand in for story messages.
            story = [line for line in horizontal if marker(line)
                     and contains(frame, coordinate(line, "x1"), coordinate(line, "y1"))
                     and contains(frame, coordinate(line, "x2"), coordinate(line, "y2"))]
            bound = set()
            for label in ("401", "200 · NEW ACCESS", "200 · BODY"):
                labels = [node for node, text in texts if text == label
                          and contains(frame, coordinate(node, "x"), coordinate(node, "y"))
                          and coordinate(node, "y") > coordinate(divider, "y1")]
                if any(positioned_children(node) for node in labels):
                    errors.append(f"response label spans must inherit their parent text position: {label!r}")
                    continue
                response = None
                if len(labels) == 1:
                    anchor = labels[0]
                    candidates = [line for line in story
                                  if coordinate(line, "y1") > coordinate(anchor, "y")
                                  and min(coordinate(line, "x1"), coordinate(line, "x2"))
                                  <= coordinate(anchor, "x")
                                  <= max(coordinate(line, "x1"), coordinate(line, "x2"))]
                    if candidates:
                        response = min(candidates, key=lambda line: coordinate(line, "y1"))
                if response not in returns or response in bound:
                    errors.append(f"missing ordinary OAuth return for visible {label!r} label")
                else:
                    bound.add(response)

        headlines = [node for node in horizontal if coordinate(node, "x1") > coordinate(node, "x2")
                     and marker(node) == "url(#arrow-accent)"]
        initial_calls = []
        if len(headlines) == 1:
            initial_calls = [line for line in horizontal if marker(line)
                             and coordinate(line, "x1") < coordinate(line, "x2")
                             and coordinate(line, "x2") == coordinate(headlines[0], "x1")
                             and coordinate(line, "y1") < coordinate(headlines[0], "y1")]
        initial_call = min(initial_calls, key=lambda line: coordinate(line, "y1")) if initial_calls else None
        if len(headlines) != 1 or initial_call is None or not any(
            coordinate(rect, "width") == 8 and contains(rect, coordinate(headlines[0], "x1"), coordinate(headlines[0], "y1"))
            # Allow the existing half-width inset at the request endpoint.
            and coordinate(rect, "y") <= coordinate(initial_call, "y1") + coordinate(rect, "width") / 2
            and any(math.isclose(coordinate(lifeline, "x1"), coordinate(rect, "x") + coordinate(rect, "width") / 2,
                                 rel_tol=0, abs_tol=1e-6)
                    and min(coordinate(lifeline, "y1"), coordinate(lifeline, "y2")) <= coordinate(initial_call, "y1")
                    and max(coordinate(lifeline, "y1"), coordinate(lifeline, "y2")) >= coordinate(headlines[0], "y1")
                    for lifeline in lifelines)
            for rect in rects
        ):
            errors.append("first API activation must span the initial call through the headline success return")
    except ValueError as exc:
        errors.append(f"cannot check OAuth geometry: {exc}")
    return errors


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def ok(msg: str) -> None:
    print(f"OK: {msg}")


def main() -> int:
    if not TYPE_SEQ.is_file():
        fail(f"missing {TYPE_SEQ}")

    text = TYPE_SEQ.read_text(encoding="utf-8")
    required_sections = [
        "## Combined fragments",
        "### Open arrowhead (async)",
        "## Complexity budget",
        "## Anti-patterns",
        "arrow-open",
    ]
    for needle in required_sections:
        if needle not in text:
            fail(f"type-sequence.md missing {needle!r}")
    for op in ("ALT", "OPT", "LOOP"):
        if op not in text:
            fail(f"type-sequence.md missing operator {op}")
    if "[token valid]" not in text and "guard" not in text.lower():
        fail("type-sequence.md missing guard documentation")
    ok("type-sequence.md fragments + async + budget present")

    for path in COLD:
        if not path.is_file():
            fail(f"cold-cache example missing: {path.name}")
        body = path.read_text(encoding="utf-8")
        if "cold cache" not in body.lower() and "Article request" not in body:
            fail(f"{path.name} no longer looks like the cold-cache example")
        if "ALT" in body and "example-sequence-oauth" not in path.name:
            # cold-cache must not grow an ALT frame (special example only)
            # allow the word only in unrelated comments; require no ALT operator tab content
            if re.search(r">ALT<", body):
                fail(f"{path.name} unexpectedly contains ALT fragment tab")
    ok("cold-cache sequence trio intact (no ALT tab)")

    for path in OAUTH:
        if not path.is_file():
            fail(f"oauth example missing: {path.name}")
        body = path.read_text(encoding="utf-8")
        findings = check_oauth(body)
        if findings:
            fail(f"{path.name}: " + "; ".join(findings))
        if "arrow-open" not in body:
            fail(f"{path.name} missing arrow-open async marker")
        if "Bearer" not in body and "BEARER" not in body:
            fail(f"{path.name} missing bearer call")
    ok("oauth trio has ALT two-region structure + async open + dashed returns")

    # Drive real skin linter entry point on new files
    cmd = [
        sys.executable,
        str(LINT),
        *[str(p) for p in OAUTH],
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    if proc.returncode != 0:
        fail(f"lint-skin.py failed on oauth examples (exit {proc.returncode})")
    if "0 finding(s)" not in proc.stdout:
        fail("lint-skin.py did not report 0 findings on oauth examples")
    ok("lint-skin.py clean on oauth examples")

    # Full repo gate
    proc2 = subprocess.run(
        [sys.executable, str(LINT), "--all", "--baseline"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    print(proc2.stdout, end="")
    if proc2.returncode != 0:
        fail(f"lint-skin.py --all --baseline failed (exit {proc2.returncode})")
    if "0 finding(s)" not in proc2.stdout:
        fail("lint-skin.py --all --baseline did not report 0 findings")
    ok("lint-skin.py --all --baseline green")

    print("ALL GATES PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
