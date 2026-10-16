#!/usr/bin/env python3
"""Structural and adversarial verification for PlantUML import.

The driver invokes the shipped extractor as a subprocess, imports its public
module surface for resource-limit checks, and verifies the documentation and
command wiring. Exit 0 only when every gate passes.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills/diagram-design/SKILL.md"
EXTRACT = ROOT / "skills/diagram-design/scripts/plantuml_extract.py"
IMPORT_REF = ROOT / "skills/diagram-design/references/import-plantuml.md"
COMMAND = ROOT / "commands/import-plantuml.md"
PROMPT = ROOT / "prompts/import-plantuml.md"
SEQUENCE = ROOT / "scripts/fixtures/sample-sequence.puml"
CLASS_FIXTURE = ROOT / "scripts/fixtures/sample-class.puml"
ADVERSARIAL = ROOT / "scripts/fixtures/sample-adversarial.puml"
MULTI = ROOT / "scripts/fixtures/sample-multi.puml"
EXAMPLE = ROOT / "skills/diagram-design/assets/example-import-plantuml.html"
OUTPUT_SPEC = ROOT / "skills/diagram-design/references/output-spec.md"
SUPPORTED_KINDS = "sequence, class"


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def ok(message: str) -> None:
    print(f"OK: {message}")


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def invoke(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(EXTRACT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def run_extract(args: list[str]) -> str:
    process = invoke(args)
    if process.returncode != 0:
        fail(
            f"extractor exited {process.returncode} for {args}: "
            f"{process.stderr.strip()}"
        )
    return process.stdout


def expect_error(args: list[str], message: str) -> None:
    process = invoke(args)
    if process.returncode != 2 or message not in process.stderr:
        fail(
            f"expected exit 2 containing {message!r} for {args}; got "
            f"{process.returncode}: {process.stderr.strip()!r}"
        )


def load_extractor_module():
    spec = importlib.util.spec_from_file_location(
        "diagram_design_plantuml_extract", EXTRACT
    )
    if spec is None or spec.loader is None:
        fail("could not load PlantUML extractor module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def spec_size_presets() -> list[str]:
    presets: list[str] = []
    in_table = False
    for line in OUTPUT_SPEC.read_text(encoding="utf-8").splitlines():
        if line.startswith("## 2. Size"):
            in_table = True
            continue
        if in_table and line.startswith("## "):
            break
        if in_table:
            match = re.match(r"\| `([a-z0-9-]+)`", line)
            if match:
                presets.append(match.group(1))
    return presets


def check_files() -> None:
    for path in (
        SKILL,
        EXTRACT,
        IMPORT_REF,
        COMMAND,
        PROMPT,
        SEQUENCE,
        CLASS_FIXTURE,
        ADVERSARIAL,
        MULTI,
        EXAMPLE,
    ):
        if not path.is_file():
            fail(f"missing {path.relative_to(ROOT)}")
    ok("all PlantUML import artifacts present")


def check_sequence() -> None:
    payload = json.loads(run_extract([str(SEQUENCE), "--json"]))
    diagram = payload["diagrams"][0]
    nodes = {node["id"]: node for node in diagram["nodes"]}
    edges = diagram["edges"]
    fragments = diagram["fragments"]

    if diagram["kind"] != "sequence":
        fail(f"sequence fixture kind was {diagram['kind']!r}")
    if len(nodes) < 3:
        fail(f"sequence fixture listed {len(nodes)} participants, expected 3+")
    for node_id, label, shape in (
        ("Client", "Client", "actor"),
        ("api", "Resource API", "lifeline"),
        ("auth", "Auth Service", "lifeline"),
    ):
        if node_id not in nodes:
            fail(f"sequence fixture missing participant {node_id}")
        if nodes[node_id]["label"] != label or nodes[node_id]["shape"] != shape:
            fail(f"sequence participant {node_id} lost display name or shape")
    labels = [edge["label"] for edge in edges]
    expected_order = [
        "GET /orders",
        "200 body",
        "401",
        "POST /token",
        "200 access",
        "GET /orders retry",
        "200 body",
        "200 body",
    ]
    if labels != expected_order:
        fail(f"sequence message order drifted: {labels}")
    alts = [item for item in fragments if item["kind"] == "alt"]
    if len(alts) != 1 or alts[0]["label"] != "token expired":
        fail(f"sequence alt fragment missing: {fragments}")
    regions = [
        (region["label"], region["first_message"], region["last_message"])
        for region in alts[0]["regions"]
    ]
    if regions != [("token expired", 3, 7), ("token valid", 8, 8)]:
        fail(f"sequence alt branches lost their message spans: {regions}")
    timeline = [
        (item["participant"], item["action"], item["after_message"])
        for item in diagram["activations"]
    ]
    if timeline[:2] != [("api", "activate", 1), ("api", "deactivate", 2)]:
        fail(f"sequence activations lost their message positions: {timeline}")
    if diagram["discarded"]["skin"] != 4:
        fail(f"sequence skinparam discard count wrong: {diagram['discarded']}")
    if not diagram["activations"]:
        fail("sequence activations were dropped")
    if "fragments" not in payload["diagrams"][0]:
        fail("--json omitted fragments")

    digest = run_extract([str(SEQUENCE), "--max-rows", "3"])
    for needle in (
        "source layout: none (PlantUML is layout-free)",
        "type candidates: sequence",
        "budget:",
        "- discarded: 4 skinparam",
        "alt(token expired) msgs 3-7; else(token valid) msg 8",
        "api:activate@1",
        "| # | source | target | label | style |",
        "### Nodes",
        "### Edges",
        "+",
    ):
        if needle not in digest:
            fail(f"sequence digest missing {needle!r}")
    ok("sequence parses: participants, order, alt, activations, skinparam ledger")


def check_class() -> None:
    payload = json.loads(run_extract([str(CLASS_FIXTURE), "--json"]))
    diagram = payload["diagrams"][0]
    nodes = {node["id"]: node for node in diagram["nodes"]}
    edges = diagram["edges"]

    if diagram["kind"] != "class":
        fail(f"class fixture kind was {diagram['kind']!r}")
    if nodes["Account"]["shape"] != "abstract":
        fail("abstract class was not classified")
    if nodes["Store"]["shape"] != "interface":
        fail("interface was not classified")
    if "+ balance(): Money" not in nodes["Account"]["fields"]:
        fail("class members were not retained")
    kinds = {edge["arrowhead"] for edge in edges}
    if "inheritance" not in kinds or "composition" not in kinds:
        fail(f"class relationship kinds missing: {kinds}")
    composition = next(edge for edge in edges if edge["arrowhead"] == "composition")
    if "1" not in composition["cardinality"] or "many" not in composition["cardinality"]:
        fail(f"composition cardinality missing: {composition}")
    if diagram["analysis"]["type_candidates"] != ["UML class"]:
        fail(f"class type candidates drifted: {diagram['analysis']['type_candidates']}")

    digest = run_extract([str(CLASS_FIXTURE)])
    if "inheritance" not in digest or "composition" not in digest:
        fail("class digest omitted relationship kinds")
    ok("class parses: members, inheritance, composition, cardinality")


def write_puml(tmp: Path, name: str, body: str) -> Path:
    path = tmp / name
    path.write_text(f"@startuml\n{body}\n@enduml\n", encoding="utf-8")
    return path


def extract_json(path: Path) -> dict:
    return json.loads(run_extract([str(path), "--json"]))["diagrams"][0]


def check_review_regressions(tmp: Path) -> None:
    """Pin the import-fidelity fixes from the PR #358 review threads."""
    # Declaration tails are parsed, never used as ids.
    diagram = extract_json(
        write_puml(
            tmp,
            "tails.puml",
            "participant A #red\nparticipant B #red\nparticipant C <<svc>> order 3\n"
            "A -> B : hi\nB -> C : go",
        )
    )
    ids = [node["id"] for node in diagram["nodes"]]
    if ids != ["A", "B", "C"]:
        fail(f"participant tails became ids: {ids}")
    if diagram["nodes"][2]["stereotype"] != "svc":
        fail("participant stereotype was not kept")
    diagram = extract_json(write_puml(tmp, "inline.puml", "class A { +id: int }\nclass B\nA --> B"))
    nodes = {node["id"]: node for node in diagram["nodes"]}
    if set(nodes) != {"A", "B"} or nodes["A"]["fields"] != ["+id: int"]:
        fail(f"inline class body became an id or lost its member: {diagram['nodes']}")
    expect_error([str(write_puml(tmp, "tail-junk.puml", "participant A extra\nA -> A : x"))], "malformed statement at line 2")
    expect_error([str(write_puml(tmp, "class-junk.puml", "class A extends B\nA --> C"))], "malformed statement at line 2")

    # Exact ids are case-sensitive.
    diagram = extract_json(write_puml(tmp, "case.puml", "participant a\nparticipant A\na -> A : ping"))
    edge = diagram["edges"][0]
    if (edge["source"], edge["target"]) != ("a", "A"):
        fail(f"letter case redirected a message: {edge}")

    # Same-named classes in different packages stay separate.
    diagram = extract_json(
        write_puml(
            tmp,
            "packages.puml",
            "package billing {\n  class User {\n    +plan\n  }\n}\n"
            "package auth {\n  class User {\n    +password\n  }\n  User --> Session\n}\n"
            "billing.User --> auth.User",
        )
    )
    nodes = {node["id"]: node for node in diagram["nodes"]}
    if nodes.get("billing.User", {}).get("fields") != ["+plan"] or nodes.get("auth.User", {}).get("fields") != ["+password"]:
        fail(f"classes merged across packages: {list(nodes)}")
    pairs = [(edge["source"], edge["target"]) for edge in diagram["edges"]]
    if pairs != [("auth.User", "Session"), ("billing.User", "auth.User")]:
        fail(f"package-qualified relationships resolved wrongly: {pairs}")
    expect_error(
        [str(write_puml(tmp, "ambiguous.puml", "package a {\n class User\n}\npackage b {\n class User\n}\nUser --> X"))],
        "ambiguous class name `User`",
    )

    # Styling commands match whole words only.
    diagram = extract_json(write_puml(tmp, "show.puml", "ShowService -> Client : result\nScale -> Client : size"))
    if [edge["label"] for edge in diagram["edges"]] != ["result", "size"]:
        fail(f"styling prefix dropped a message: {diagram['edges']}")
    diagram = extract_json(write_puml(tmp, "show-member.puml", "class View {\n  show(): void\n  hide(): void\n}"))
    if diagram["nodes"][0]["fields"] != ["show(): void", "hide(): void"]:
        fail(f"styling prefix dropped class members: {diagram['nodes'][0]['fields']}")

    # Multi-line styling blocks are consumed whole.
    diagram = extract_json(
        write_puml(
            tmp,
            "skin-block.puml",
            "skinparam sequence {\n  ArrowColor red\n  LifeLineBorderColor blue\n}\n"
            "legend right\n  shorthand\nendlegend\nAlice -> Bob : hi",
        )
    )
    if [edge["label"] for edge in diagram["edges"]] != ["hi"] or diagram["discarded"]["skin"] != 2:
        fail(f"multiline styling block was not consumed: {diagram['discarded']}")
    expect_error([str(write_puml(tmp, "skin-open.puml", "Alice -> Bob : hi\nskinparam sequence {\n  ArrowColor red"))], "unterminated styling block at line 3")

    # Open class or package bodies fail instead of swallowing relationships.
    expect_error([str(write_puml(tmp, "brace.puml", "class A {\n  +id\nA --> B"))], "unterminated class body at line 2")
    expect_error([str(write_puml(tmp, "package-open.puml", "package p {\n  class A\nA --> B"))], "unterminated package at line 2")

    # Region splitting honors block comments.
    commented = tmp / "comment-end.puml"
    commented.write_text(
        "@startuml\nAlice -> Bob : one\n/'\n@enduml\n'/\nBob -> Alice : two\n@enduml\n",
        encoding="utf-8",
    )
    diagram = extract_json(commented)
    if [edge["label"] for edge in diagram["edges"]] != ["one", "two"]:
        fail(f"@enduml inside a block comment cut the diagram short: {diagram['edges']}")
    open_comment = tmp / "comment-open.puml"
    open_comment.write_text("@startuml\nAlice -> Bob : one\n/'\n@enduml\n", encoding="utf-8")
    expect_error([str(open_comment)], "unterminated block comment at line 3")

    # Stereotypes reach the default digest.
    digest = run_extract([str(write_puml(tmp, "stereo.puml", "class Account <<entity>>\nclass Ledger\nLedger --> Account"))])
    if "| Account | Account | class | entity |" not in digest:
        fail(f"class stereotype missing from the default digest: {digest!r}")
    ok("review regressions: timeline positions, declaration tails, case, packages, styling, braces, comments, stereotypes")


def check_kind_detection_skips_bodies(tmp: Path) -> None:
    """Note, legend, and class bodies are text, not statements, when picking the kind."""
    diagram = extract_json(
        write_puml(
            tmp,
            "note-body-kind.puml",
            "participant A\nparticipant B\nnote over A\n  class Foo\n  interface Bar\nend note\n"
            "legend\n  class Legend\nendlegend\nA -> B : hi",
        )
    )
    if diagram["kind"] != "sequence" or [edge["label"] for edge in diagram["edges"]] != ["hi"]:
        fail(f"note or legend body changed the diagram kind: {diagram['kind']}")
    if "class Foo\ninterface Bar" not in diagram["notes"]:
        fail(f"multiline note body was not kept as note text: {diagram['notes']}")
    diagram = extract_json(
        write_puml(
            tmp,
            "member-kind.puml",
            "class Casting {\n  participant: Person\n  actor: Role\n}\nclass Person\nCasting --> Person",
        )
    )
    if diagram["kind"] != "class" or diagram["nodes"][0]["fields"] != ["participant: Person", "actor: Role"]:
        fail(f"class members that look like declarations changed the kind: {diagram['kind']}")
    ok("kind detection ignores note, legend, and class body text")


def check_digest_edges_use_ids(tmp: Path) -> None:
    """Same-named classes stay distinguishable in the default digest."""
    source = write_puml(
        tmp,
        "edge-ids.puml",
        "package billing {\n  class User\n}\npackage auth {\n  class User\n}\n"
        "billing.User --> auth.User : syncs",
    )
    digest = run_extract([str(source)])
    row = r"| 1 | billing\.User \(User\) | auth\.User \(User\) | syncs |"
    if row not in digest:
        fail(f"edge table lost the class ids of its endpoints: {digest!r}")
    if r"- entry points: billing\.User \(User\)" not in digest:
        fail(f"entry points lost the class id: {digest!r}")
    sequence = run_extract([str(SEQUENCE)])
    if r"| 1 | Client | api \(Resource API\) | GET /orders |" not in sequence:
        fail(f"sequence edge table lost participant ids: {sequence!r}")
    ok("digest edges and summaries name endpoints by id, with the label alongside")


def check_unselected_comment_isolated(tmp: Path) -> None:
    """An unclosed block comment fails only the block that contains it."""
    source = tmp / "unselected-comment.puml"
    source.write_text(
        "@startuml\nAlice -> Bob : one\n@enduml\n\n"
        "@startuml\nCarol -> Dan : two\n/'\nnever closed\n@enduml\n",
        encoding="utf-8",
    )
    for args in ([str(source)], [str(source), "--diagram", "0"]):
        digest = run_extract(args)
        if "[1] unparsed: unterminated block comment at line 7" not in digest:
            fail(f"unselected block with an open comment was not listed as unparsed: {digest!r}")
        if "## Diagram 0" not in digest:
            fail("selected block was not emitted past an open comment elsewhere")
    expect_error([str(source), "--diagram", "1"], "unterminated block comment at line 7")
    expect_error([str(source), "--diagram", "all"], "unterminated block comment at line 7")
    fenced = tmp / "unselected-comment.md"
    fenced.write_text(
        "```plantuml\n@startuml\nAlice -> Bob : one\n@enduml\n```\n\n"
        "```plantuml\n@startuml\nCarol -> Dan : two\n/'\n@enduml\n```\n",
        encoding="utf-8",
    )
    if "## Diagram 0" not in run_extract([str(fenced), "--diagram", "0"]):
        fail("fenced block 0 was blocked by an open comment in fenced block 1")
    expect_error([str(fenced), "--diagram", "1"], "unterminated block comment at line 10")
    ok("an unclosed block comment fails only its own block")


def check_generics_survive(tmp: Path) -> None:
    """Type parameters are content, not markup, in classes, members, and messages."""
    source = write_puml(
        tmp,
        "generics.puml",
        "class Box<T>\nclass Ref<a>\nclass Map<K, V> {\n  - entries: List<Entry<K, V>>\n  + get(key: K): Optional<V>\n}\n"
        "Box --> Map\nRef --> Box",
    )
    diagram = extract_json(source)
    nodes = {node["id"]: node for node in diagram["nodes"]}
    labels = [nodes.get(key, {}).get("label") for key in ("Box", "Ref", "Map")]
    if labels != ["Box<T>", "Ref<a>", "Map<K, V>"]:
        fail(f"generic class parameters were erased: {diagram['nodes']}")
    if nodes["Map"]["fields"] != ["- entries: List<Entry<K, V>>", "+ get(key: K): Optional<V>"]:
        fail(f"generic member types were erased: {nodes['Map']['fields']}")
    digest = run_extract([str(source)])
    if r"| Box | Box&lt;T&gt; | class |" not in digest:
        fail(f"digest dropped or failed to escape the generic parameter: {digest!r}")
    diagram = extract_json(
        write_puml(
            tmp,
            "generic-message.puml",
            "A -> B : load(): List<Order>\n"
            "note over A: <SCRIPT>x</SCRIPT> &lt;script&gt;y <b>bold</b> <color:red>red</color>",
        )
    )
    if diagram["edges"][0]["label"] != "load(): List<Order>":
        fail(f"generic text in a message label was erased: {diagram['edges'][0]}")
    if "<script" in json.dumps(diagram).casefold() or "x y bold red" not in diagram["notes"][0]:
        fail(f"markup cleanup let a script tag through or lost text: {diagram['notes']}")
    ok("generic parameters survive in labels, members, messages, and the digest")


def check_cardinality_ends(tmp: Path) -> None:
    """Each cardinality stays on the class it was written next to."""
    def ends(body: str, name: str) -> tuple[tuple[str, str, str, str], str]:
        source = write_puml(tmp, name, "class A\nclass B\n" + body)
        edge = extract_json(source)["edges"][0]
        row = next(line for line in run_extract([str(source)]).splitlines() if line.startswith("| 1 |"))
        return (
            edge["source"],
            edge["target"],
            edge.get("source_cardinality"),
            edge.get("target_cardinality"),
        ), row

    left, left_row = ends('A "1" --> B : owns', "card-left.puml")
    right, right_row = ends('A --> "1" B : owns', "card-right.puml")
    if left != ("A", "B", "1", "") or right != ("A", "B", "", "1"):
        fail(f"one-sided cardinality lost its end: {left} vs {right}")
    if "cardinality 1 (source)" not in left_row or "cardinality 1 (target)" not in right_row:
        fail(f"digest cannot tell which end owns the cardinality: {left_row!r} / {right_row!r}")
    reverse, _row = ends('A "1" <|-- "many" B', "card-reverse.puml")
    if reverse != ("B", "A", "many", "1"):
        fail(f"reverse arrow moved a cardinality to the wrong class: {reverse}")
    # PlantUML writes a cardinality between the class and the arrow; one
    # after the far class is not a cardinality, so it fails by line.
    expect_error(
        [str(write_puml(tmp, "card-after.puml", 'class A\nclass B\nA --> B "1"'))],
        "malformed edge at line 4",
    )
    ok("source and target cardinalities stay separate in JSON and the digest")


def check_note_placement(tmp: Path) -> None:
    """Sequence notes keep every covered participant and their message position."""
    source = write_puml(
        tmp,
        "note-placement.puml",
        "participant A\nparticipant B\nparticipant C\nA -> B : one\n"
        "note over A, B: shared transaction\nB -> C : two\nnote right of C #aqua: colored\n"
        "note left: on message two\nnote over B, C\n  spans\nend note\nnote across: everyone",
    )
    diagram = extract_json(source)
    if [node["id"] for node in diagram["nodes"]] != ["A", "B", "C"]:
        fail(f"a note target invented a participant: {[node['id'] for node in diagram['nodes']]}")
    placements = [
        (item["text"], item["position"], item["participants"], item["after_message"], item["message"])
        for item in diagram.get("note_details", [])
    ]
    expected = [
        ("shared transaction", "over", ["A", "B"], 1, None),
        ("colored", "right", ["C"], 2, None),
        ("on message two", "left", [], 2, 2),
        ("spans", "over", ["B", "C"], 2, None),
        ("everyone", "across", [], 2, None),
    ]
    if placements != expected:
        fail(f"notes lost their participants or message position: {placements}")
    digest = run_extract([str(source)])
    if "over A, B @1: shared transaction" not in digest or "left of msg 2: on message two" not in digest:
        fail(f"digest notes lost their placement: {digest!r}")
    expect_error(
        [str(write_puml(tmp, "note-orphan.puml", "participant A\nnote left: nothing yet\nA -> A : x"))],
        "malformed statement at line 3",
    )
    ok("sequence notes keep all covered participants and their message position")


def check_activation_shortcuts(tmp: Path) -> None:
    """`++`, `**`, `!!` change the receiver and `--` the sender, also on reverse arrows."""
    diagram = extract_json(
        write_puml(
            tmp,
            "activation-shortcuts.puml",
            "participant A\nparticipant B\nparticipant C\nparticipant D\n"
            "A -> B ++ : hello\nA <- B ++ : call\nB -> C --++ : hand off\nC --> A -- : ok\n"
            "B <-- C -- : back\nA -> D ** : create\nA -> D !! : delete\nA -> B ++ #gold : tinted",
        )
    )
    if [node["id"] for node in diagram["nodes"]] != ["A", "B", "C", "D"]:
        fail(f"activation shortcut text became a participant: {[node['id'] for node in diagram['nodes']]}")
    timeline = [
        (item["participant"], item["action"], item["after_message"])
        for item in diagram["activations"]
    ]
    expected = [
        ("B", "activate", 1),
        ("A", "activate", 2),
        ("B", "deactivate", 3),
        ("C", "activate", 3),
        ("C", "deactivate", 4),
        ("C", "deactivate", 5),
        ("D", "create", 6),
        ("D", "destroy", 7),
        ("B", "activate", 8),
    ]
    if timeline != expected:
        fail(f"activation shortcuts landed on the wrong lifeline: {timeline}")
    expect_error(
        [str(write_puml(tmp, "activation-left.puml", "participant A\nparticipant B\nA ++ <- B : call"))],
        "malformed edge at line 4",
    )
    ok("activation shortcuts follow the message's sender and receiver on reverse arrows")


def check_whole_arrows(tmp: Path) -> None:
    """Arrows parse whole; fragments never become participant or class names."""
    diagram = extract_json(
        write_puml(
            tmp,
            "seq-arrows.puml",
            "participant A\nparticipant B\nA ---> B : long\nA -[#red]> B : colored\n"
            "A -[#blue]-> B : colored dashed\nA ->> B : async\nA <-> B : both\nA ->x B : lost\n"
            "B <-- A : back\nA->B: tight",
        )
    )
    if [node["id"] for node in diagram["nodes"]] != ["A", "B"]:
        fail(f"sequence arrow fragments became participants: {[node['id'] for node in diagram['nodes']]}")
    shapes = [
        (edge["source"], edge["target"], edge["style"], edge["arrowhead"], edge["bidirectional"])
        for edge in diagram["edges"]
    ]
    expected = [
        ("A", "B", "dashed", "arrow", False),
        ("A", "B", "solid", "arrow", False),
        ("A", "B", "dashed", "arrow", False),
        ("A", "B", "solid", "async", False),
        ("A", "B", "solid", "arrow", True),
        ("A", "B", "solid", "lost", False),
        ("A", "B", "dashed", "arrow", False),
        ("A", "B", "solid", "arrow", False),
    ]
    if shapes != expected:
        fail(f"sequence arrows parsed wrongly: {shapes}")
    for name, body, message in (
        ("seq-chain.puml", "participant A\nA -> B -> C : chain", "malformed edge at line 3"),
        ("seq-space.puml", "participant A\nA -> B C : x", "malformed edge at line 3"),
        ("seq-quoted-tail.puml", 'participant A\nA "1" -> B : x', "malformed edge at line 3"),
        ("seq-boundary.puml", "participant A\n[-> A : start", "unsupported sequence construct: boundary message at line 3"),
    ):
        expect_error([str(write_puml(tmp, name, body))], message)

    diagram = extract_json(
        write_puml(
            tmp,
            "class-arrows.puml",
            "class A\nclass B\nA ---> B\nA -up-> B\nA -[#red]-> B\nA .> B\n"
            'A "1" *--> "many" B\nA -[hidden]- B\nB <|... A\nA --o B',
        )
    )
    if [node["id"] for node in diagram["nodes"]] != ["A", "B"]:
        fail(f"class arrow fragments became classes: {[node['id'] for node in diagram['nodes']]}")
    shapes = [
        (edge["source"], edge["target"], edge["style"], edge["arrowhead"])
        for edge in diagram["edges"]
    ]
    expected = [
        ("A", "B", "solid", "association"),
        ("A", "B", "solid", "association"),
        ("A", "B", "solid", "association"),
        ("A", "B", "dashed", "association"),
        ("A", "B", "solid", "composition"),
        ("A", "B", "dashed", "inheritance"),
        ("B", "A", "solid", "aggregation"),
    ]
    if shapes != expected or diagram["discarded"]["skin"] != 1:
        fail(f"class arrows parsed wrongly: {shapes} {diagram['discarded']}")
    for name, body, message in (
        ("class-chain.puml", "class A\nA --> B --> C", "malformed edge at line 3"),
        ("class-space.puml", "class A\nA --> B C", "malformed edge at line 3"),
        ("class-head.puml", "class A\nA x-- B", "unsupported relationship arrow `x--` at line 3"),
    ):
        expect_error([str(write_puml(tmp, name, body))], message)
    ok("arrows parse whole (long, styled, directed, decorated) and malformed ones fail by line")


def check_command_word_messages(tmp: Path) -> None:
    """A message or link whose endpoint is a styling command word is content."""
    diagram = extract_json(
        write_puml(
            tmp,
            "show-messages.puml",
            "participant B\nhide footbox\nshow -> B : one\nShow --> B : two\nshow->B : three\n"
            "B <- show : four\nshow -[#red]> B : five\nheader -> B : six",
        )
    )
    labels = [edge["label"] for edge in diagram["edges"]]
    if labels != ["one", "two", "three", "four", "five", "six"] or diagram["discarded"]["skin"] != 1:
        fail(f"a message starting with a styling word was dropped: {labels} {diagram['discarded']}")
    diagram = extract_json(
        write_puml(tmp, "show-links.puml", "class B\nhide empty members\nshow --> B\nhide <|-- B\nshow B fields")
    )
    links = [(edge["source"], edge["target"]) for edge in diagram["edges"]]
    if links != [("show", "B"), ("B", "hide")] or diagram["discarded"]["skin"] != 2:
        fail(f"a class link starting with a styling word was dropped: {links} {diagram['discarded']}")
    ok("messages and links named after styling commands survive; the commands are still discarded")


def check_activation_keyword_colors(tmp: Path) -> None:
    """`activate A #red` activates A; the color never becomes a participant."""
    diagram = extract_json(
        write_puml(tmp, "activate-color.puml", "participant A\nactivate A #red\nA -> A : x\ndeactivate A\ndestroy A")
    )
    timeline = [(item["participant"], item["action"]) for item in diagram["activations"]]
    if [node["id"] for node in diagram["nodes"]] != ["A"] or timeline != [("A", "activate"), ("A", "deactivate"), ("A", "destroy")]:
        fail(f"activation color became a participant: {[node['id'] for node in diagram['nodes']]} {timeline}")
    expect_error(
        [str(write_puml(tmp, "activate-two.puml", "participant A\nactivate A B\nA -> A : x"))],
        "malformed statement at line 3",
    )
    ok("activate/deactivate drop a color and refuse extra names")


def check_together_is_layout_only(tmp: Path) -> None:
    """`together { }` groups classes for layout; it is not a package."""
    diagram = extract_json(
        write_puml(
            tmp,
            "together.puml",
            "together {\n  class A\n  class B\n}\npackage p {\n  together {\n    class C\n  }\n}\nA --> B\nB --> p.C",
        )
    )
    nodes = [(node["id"], node["parent"]) for node in diagram["nodes"]]
    if nodes != [("A", None), ("B", None), ("p", None), ("p.C", "p")]:
        fail(f"together became a package: {nodes}")
    ok("together blocks add no container and do not qualify class ids")


def check_inline_block_comments(tmp: Path) -> None:
    """A `/' ... '/` comment inside a line is not label text, and one opened mid-line hides what follows."""
    diagram = extract_json(
        write_puml(
            tmp,
            "inline-comment.puml",
            "A -> B : x /' hidden '/\nA -> B : y /' opens\nC -> D : hidden\n'/ B -> A : z",
        )
    )
    edges = [(edge["source"], edge["target"], edge["label"]) for edge in diagram["edges"]]
    if edges != [("A", "B", "x"), ("A", "B", "y"), ("B", "A", "z")]:
        fail(f"inline block comment leaked into the diagram: {edges}")
    ok("inline and mid-line block comments are removed like whole-line ones")


def check_quoted_name_cardinality(tmp: Path) -> None:
    """A quoted class name next to a cardinality keeps both in their places."""
    diagram = extract_json(
        write_puml(
            tmp,
            "quoted-card.puml",
            'class "My A"\nclass "My B"\n"My A" "1" --> "many" "My B"',
        )
    )
    edge = diagram["edges"][0]
    got = (edge["source"], edge["target"], edge["source_cardinality"], edge["target_cardinality"])
    if [node["id"] for node in diagram["nodes"]] != ["My A", "My B"] or got != ("My A", "My B", "1", "many"):
        fail(f"a quoted class name swapped places with its cardinality: {got}")
    expect_error(
        [str(write_puml(tmp, "card-outside.puml", 'class A\nclass B\n"1" A --> B'))],
        "malformed edge at line 4",
    )
    ok("cardinality is read next to the arrow, so quoted class names stay names")


def check_kind_uses_arrow_parser(tmp: Path) -> None:
    """Every arrow the parsers accept also decides the kind on its own."""
    for name, body, kind, count in (
        ("kind-seq-color.puml", "A -[#red]> B : hi", "sequence", 1),
        ("kind-seq-color-dashed.puml", "A -[#blue]-> B : hi", "sequence", 1),
        ("kind-class-color.puml", "Base <|-[#red]- Child", "class", 1),
        ("kind-class-dotted.puml", "Whole *.. Part", "class", 1),
        ("kind-class-hint.puml", "Base <|-up- Child", "class", 1),
    ):
        diagram = extract_json(write_puml(tmp, name, body))
        if diagram["kind"] != kind or len(diagram["edges"]) != count:
            fail(f"{body!r} was detected as {diagram['kind']} with {len(diagram['edges'])} edges")
    ok("kind detection reads arrows with the same parser as the edge parsers")


def check_quoted_note_targets(tmp: Path) -> None:
    """A colon inside a quoted note target is part of the name, not the body separator."""
    diagram = extract_json(
        write_puml(
            tmp,
            "note-quoted-colon.puml",
            'participant "A:B"\nparticipant C\n"A:B" -> C : x\nnote over "A:B": text\n'
            'note over "A:B", C: both\nnote right of "A:B"\n  multi: line\nend note',
        )
    )
    placements = [(item["text"], item["participants"]) for item in diagram["note_details"]]
    if placements != [("text", ["A:B"]), ("both", ["A:B", "C"]), ("multi: line", ["A:B"])]:
        fail(f"a colon in a quoted note target split the note: {placements}")
    diagram = extract_json(
        write_puml(tmp, "class-note-quoted.puml", 'class "Svc:Main"\nnote right of "Svc:Main" : hi: there')
    )
    if [(item["text"], item["participants"]) for item in diagram["note_details"]] != [("hi: there", ["Svc:Main"])]:
        fail(f"a colon in a quoted class note target split the note: {diagram['note_details']}")
    ok("note bodies split at the first colon outside quotes")


def check_endpoint_codes(tmp: Path) -> None:
    """Endpoints resolve by their raw PlantUML code; cleanup only shapes the label.

    PlantUML looks a participant or class up by code: a bare name, or the text
    inside quotes. A display name given with `as` is a label, not a second code.
    """
    diagram = extract_json(
        write_puml(
            tmp,
            "endpoint-codes.puml",
            'participant "A" as X\nparticipant A\nX -> "A" : by code\n"**A**" -> X : formatted\n'
            '"Long" as L -> X : inline long\nX -> M as "Mid" : inline code\nL -> "Long" : quoted code\n'
            "C <- D : reverse",
        )
    )
    nodes = [(node["id"], node["label"]) for node in diagram["nodes"]]
    expected_nodes = [
        ("X", "A"), ("A", "A"), ("**A**", "A"), ("L", "Long"), ("M", "Mid"), ("Long", "Long"), ("C", "C"), ("D", "D"),
    ]
    if nodes != expected_nodes:
        fail(f"sequence endpoints resolved by cleaned or display text: {nodes}")
    pairs = [(edge["source"], edge["target"]) for edge in diagram["edges"]]
    if pairs != [("X", "A"), ("**A**", "X"), ("L", "X"), ("X", "M"), ("L", "Long"), ("D", "C")]:
        fail(f"sequence messages connected the wrong participants: {pairs}")
    diagram = extract_json(
        write_puml(tmp, "class-codes.puml", 'class "A" as X\nclass A\nX --> "A"\n"**A**" --> X')
    )
    nodes = [(node["id"], node["label"]) for node in diagram["nodes"]]
    pairs = [(edge["source"], edge["target"]) for edge in diagram["edges"]]
    if nodes != [("X", "A"), ("A", "A"), ("**A**", "A")] or pairs != [("X", "A"), ("**A**", "X")]:
        fail(f"class relationships resolved by cleaned or display text: {nodes} {pairs}")
    ok("endpoints resolve by raw code, inline `as` declarations work, labels are cleaned separately")


def check_region_boundaries(tmp: Path) -> None:
    """A block must close with its own `@end` marker; failures stay on that block."""
    def source(name: str, text: str) -> str:
        path = tmp / name
        path.write_bytes(text.encode("utf-8"))
        return str(path)

    unclosed = source("unclosed.puml", "@startuml\nA -> B : one\n@enduml\n\n@startuml\nC -> D : two\n")
    digest = run_extract([unclosed])
    if "[1] unparsed: missing @enduml for @startuml at line 5" not in digest or "## Diagram 0" not in digest:
        fail(f"a block with no closing marker was accepted or blocked the others: {digest!r}")
    expect_error([unclosed, "--diagram", "1"], "missing @enduml for @startuml at line 5")
    expect_error(
        [source("mismatched.puml", "@startuml\nA -> B : one\n@endjson\n")],
        "`@endjson` at line 3 does not close `@startuml` at line 1",
    )
    expect_error(
        [source("nested.puml", "@startuml\nA -> B : one\n@startuml\nB -> A : two\n@enduml\n")],
        "nested @startuml at line 3",
    )
    diagram = extract_json(
        Path(source("bom-crlf.puml", "\ufeff@startuml mydiagram  \r\nA -> B : one\r\n  @enduml  \r\n"))
    )
    if [edge["label"] for edge in diagram["edges"]] != ["one"]:
        fail(f"BOM, CRLF, a diagram name, or padded markers broke the block: {diagram['edges']}")
    fenced = source(
        "fenced-bom.md",
        "\ufeff# Notes\r\n\r\n```plantuml\r\n@startuml\r\nA -> B : one\r\n@enduml\r\n```\r\n",
    )
    if [edge["label"] for edge in extract_json(Path(fenced))["edges"]] != ["one"]:
        fail("a fenced block with a BOM and CRLF line endings did not parse")
    ok("blocks need their own @end marker, nesting fails, and BOM/CRLF/names/padding are accepted")


def check_keyword_named_endpoints(tmp: Path) -> None:
    """A participant or class named after a command word still sends and links."""
    diagram = extract_json(
        write_puml(
            tmp,
            "keyword-endpoints.puml",
            "participant note\nparticipant activate\nparticipant participant\n"
            "note -> activate : one\nactivate -> participant : two\nparticipant --> note : three",
        )
    )
    pairs = [(edge["source"], edge["target"], edge["label"]) for edge in diagram["edges"]]
    if pairs != [("note", "activate", "one"), ("activate", "participant", "two"), ("participant", "note", "three")]:
        fail(f"a message from a command-named participant was misread: {pairs}")
    diagram = extract_json(write_puml(tmp, "keyword-classes.puml", "class class\nclass enum\nclass --> enum"))
    if [(edge["source"], edge["target"]) for edge in diagram["edges"]] != [("class", "enum")]:
        fail(f"a link from a command-named class was misread: {diagram['edges']}")
    ok("participants and classes named after command words keep their messages and links")


def check_fences_follow_markdown(tmp: Path) -> None:
    """A plantuml fence quoted inside another fence is example text, not a diagram."""
    source = tmp / "nested-fence.md"
    source.write_text(
        "````markdown\n```plantuml\n@startuml\nA -> B : example\n@enduml\n```\n````\n\n"
        "```plantuml\n@startuml\nC -> D : real\n@enduml\n```\n",
        encoding="utf-8",
    )
    payload = json.loads(run_extract([str(source), "--diagram", "all", "--json"]))
    labels = [[edge["label"] for edge in item["edges"]] for item in payload["diagrams"]]
    if payload["diagrams_total"] != 1 or labels != [["real"]]:
        fail(f"a plantuml fence inside another fence was imported: {labels}")
    ok("only top-level plantuml fences are imported, matching the Mermaid importer")


def check_command_named_kind(tmp: Path) -> None:
    """An arrow line is an edge whatever its endpoints are named, for kind detection too."""
    diagram = extract_json(
        write_puml(tmp, "kind-command-seq.puml", "participant class\nparticipant B\nclass -> B : hi")
    )
    if diagram["kind"] != "sequence" or [(e["source"], e["target"]) for e in diagram["edges"]] != [("class", "B")]:
        fail(f"a participant named `class` changed the kind: {diagram['kind']}")
    diagram = extract_json(
        write_puml(tmp, "kind-command-class.puml", "class participant\nclass B\nparticipant --> B")
    )
    if diagram["kind"] != "class" or [(e["source"], e["target"]) for e in diagram["edges"]] != [("participant", "B")]:
        fail(f"a class named `participant` changed the kind: {diagram['kind']}")
    ok("arrow lines are edges before declarations, in kind detection and parsing")


def check_detection_matches_parsers(tmp: Path) -> None:
    """Differential: kind detection and the selected parser classify every line alike.

    Runs over every fixture and every input the other checks wrote. A line the
    parser treats as an edge must be an edge for detection, and a line detection
    counts as a declaration of the chosen kind must be a declaration to the parser.
    """
    extractor = load_extractor_module()
    sources = sorted(tmp.rglob("*.puml")) + sorted(tmp.rglob("*.md"))
    sources += [SEQUENCE, CLASS_FIXTURE, ADVERSARIAL, MULTI]
    compared = 0
    for path in sources:
        try:
            blocks = extractor.load_blocks(path)
        except extractor.ExtractError:
            continue
        for block in blocks:
            try:
                diagram = extractor.parse_block(block)
            except extractor.ExtractError:
                continue
            detected = diagram.detected_roles
            parsed = diagram.parsed_roles
            for line in sorted(set(detected) | set(parsed)):
                seen, used = detected.get(line), parsed.get(line)
                if (seen == "edge") != (used == "edge") or (seen == "declaration" and used != "declaration"):
                    fail(
                        f"{path.name} block {block.index} line {line}: detection read "
                        f"{seen!r} but the {diagram.kind} parser read {used!r}"
                    )
            compared += 1
    if compared < 40:
        fail(f"differential check compared only {compared} diagrams")
    ok(f"kind detection and the parsers agree on every line of {compared} diagrams")


def check_declaration_styling(tmp: Path) -> None:
    """Every declaration kind reads name, alias, color, and stereotype the same way."""
    diagram = extract_json(
        write_puml(
            tmp,
            "decl-sequence.puml",
            'participant "Pay API" as pay #orange\nactor User <<human>>\n'
            'database "Ledger DB" as db <<store>> #line:red;line.dashed\nqueue Q ##[dashed]blue <<bus>> order 3\n'
            "User -> pay : buy\npay -> db : write\npay -> Q : emit",
        )
    )
    nodes = [(n["id"], n["label"], n["shape"], n["stereotype"]) for n in diagram["nodes"]]
    if nodes != [
        ("pay", "Pay API", "lifeline", ""),
        ("User", "User", "actor", "human"),
        ("db", "Ledger DB", "lifeline", "store"),
        ("Q", "Q", "lifeline", "bus"),
    ]:
        fail(f"participant styling leaked into names: {nodes}")
    diagram = extract_json(
        write_puml(
            tmp,
            "decl-class.puml",
            'package "Billing" as billing #orange {\n  class User #pink\n}\n'
            "namespace core <<Folder>> #EEE {\n  interface Store <<port>> #line:blue\n}\n"
            'abstract class "Base Account" as Base <<entity>> #pink {\n  +id\n}\n'
            "enum Kind <<code>>\nbilling.User --> Session\nbilling.User --> core.Store\nBase --> Kind",
        )
    )
    nodes = [(n["id"], n["label"], n["shape"], n["parent"], n["stereotype"]) for n in diagram["nodes"]]
    expected = [
        ("billing", "Billing", "container", None, ""),
        ("billing.User", "User", "class", "billing", ""),
        ("core", "core", "container", None, "Folder"),
        ("core.Store", "Store", "interface", "core", "port"),
        ("Base", "Base Account", "abstract", None, "entity"),
        ("Kind", "Kind", "enum", None, "code"),
        ("Session", "Session", "class", None, ""),
    ]
    if nodes != expected:
        fail(f"class or package styling leaked into names: {nodes}")
    pairs = [(e["source"], e["target"]) for e in diagram["edges"]]
    if pairs != [("billing.User", "Session"), ("billing.User", "core.Store"), ("Base", "Kind")]:
        fail(f"a styled package redirected its links: {pairs}")
    for name, body, line in (
        ("decl-p-junk.puml", "participant A #red extra\nA -> A : x", 2),
        ("decl-c-junk.puml", "class A <<x>> extra\nclass B\nA --> B", 2),
        ("decl-pkg-junk.puml", "package p as q extra {\n  class A\n}", 2),
        ("decl-pkg-two-alias.puml", 'package "P" as p q {\n  class A\n}', 2),
        ("decl-ns-junk.puml", "namespace n #red junk {\n  class A\n}", 2),
    ):
        expect_error([str(write_puml(tmp, name, body))], f"malformed statement at line {line}")
    ok("declarations read one name and alias, drop color and keep stereotype, and reject leftovers")


def check_block_errors_stay_local(tmp: Path) -> None:
    """Every split or scan failure belongs to its block: block 0 still imports."""
    valid = "@startuml\nAlice -> Bob : one\n@enduml\n"
    fence = "```plantuml\n@startuml\nAlice -> Bob : one\n@enduml\n```\n\n"
    cases = (
        ("local-comment.puml", valid + "@startuml\nC -> D : x\n/'\n@enduml\n", "unterminated block comment at line 6"),
        ("local-missing-end.puml", valid + "@startuml\nC -> D : x\n", "missing @enduml for @startuml at line 4"),
        ("local-mismatch.puml", valid + "@startuml\nC -> D : x\n@endjson\n", "`@endjson` at line 6 does not close"),
        ("local-nested.puml", valid + "@startuml\n@startuml\nC -> D : x\n@enduml\n", "nested @startuml at line 5"),
        ("local-kind.puml", valid + "@startgantt\nProject starts 2026-01-01\n@endgantt\n", "unsupported diagram kind"),
        ("local-include.puml", valid + "@startuml\n!include other.puml\n@enduml\n", "include not inlined"),
        ("local-fence-open.md", fence + "```plantuml\n@startuml\nC -> D : x\n@enduml\n", "unterminated plantuml fence starting at line 7"),
        ("local-fence-comment.md", fence + "```plantuml\n@startuml\n/'\n@enduml\n```\n", "unterminated block comment at line 9"),
        ("local-fence-end.md", fence + "```plantuml\n@startuml\nC -> D : x\n```\n", "missing @enduml for @startuml at line 8"),
    )
    for name, text, message in cases:
        path = tmp / name
        path.write_text(text, encoding="utf-8")
        digest = run_extract([str(path), "--diagram", "0"])
        if "## Diagram 0" not in digest or f"[1] unparsed: {_escape_digest(message)}" not in digest:
            fail(f"{name}: block 1's error was not kept on block 1: {digest!r}")
        expect_error([str(path), "--diagram", "1"], message)
    ok(f"{len(cases)} block-level failures stay on their block and fire only when it is selected")


def _escape_digest(text: str) -> str:
    """The digest escapes Markdown punctuation; match its form of a message."""
    return re.sub(r"([\\`*{}\[\]()#+\-.!_|>])", r"\\\1", text.replace("&", "&amp;").replace("<", "&lt;"))


def check_declaration_edge_forms(tmp: Path) -> None:
    """A generic before an alias, and `<<...>>` inside a quoted name, survive the tokenizer."""
    diagram = extract_json(write_puml(tmp, "decl-generic-alias.puml", "class Box<T> as B #pink <<e>>\nB --> C"))
    first = diagram["nodes"][0]
    if (first["id"], first["label"], first["stereotype"]) != ("B", "Box<T>", "e"):
        fail(f"a generic before `as` broke the declaration: {first}")
    diagram = extract_json(write_puml(tmp, "decl-quoted-angle.puml", 'participant "a <<b>> c" as X\nX -> X : x'))
    if diagram["nodes"][0]["label"] != "a <<b>> c":
        fail(f"`<<b>>` inside a quoted name was read as markup: {diagram['nodes'][0]['label']!r}")
    diagram = extract_json(write_puml(tmp, "decl-quoted-script.puml", 'participant "x <<script>> y" as S\nS -> S : z'))
    if "<script" in json.dumps(diagram).casefold():
        fail(f"a doubled script tag crossed into JSON: {diagram['nodes'][0]['label']!r}")
    ok("generic-then-alias declarations and `<<...>>` inside quoted names keep their text")


def check_multi_diagram() -> None:
    payload = json.loads(run_extract([str(MULTI), "--diagram", "1", "--json"]))
    if payload["diagrams_total"] != 2:
        fail(f"diagrams_total must count every block: {payload['diagrams_total']}")
    if [(item["index"], item["kind"]) for item in payload["diagrams"]] != [(1, "class")]:
        fail("--diagram 1 did not return block 1 past a malformed block 0")
    digest = run_extract([str(MULTI), "--diagram", "1"])
    if "[0] unparsed: include not inlined" not in digest:
        fail(f"unselected include block was not listed as unparsed: {digest!r}")
    if "## Diagram 1" not in digest or "## Diagram 0" in digest:
        fail("selected-block digest emitted the wrong diagram")
    expect_error([str(MULTI), "--diagram", "0"], "include not inlined")
    expect_error([str(MULTI)], "include not inlined")
    expect_error([str(MULTI), "--diagram", "9"], "no diagram with index 9 (have 0..1)")
    ok("--diagram 1 isolates a class block past a malformed include in block 0")


def check_adversarial(tmp: Path) -> None:
    payload = json.loads(run_extract([str(ADVERSARIAL), "--json"]))
    diagram = payload["diagrams"][0]
    notes = " ".join(diagram["notes"])
    if "IGNORE ALL PREVIOUS INSTRUCTIONS" not in notes:
        fail("prompt-injection note was not retained as inert diagram text")
    if "javascript:" not in notes:
        fail("javascript: note text was dropped instead of kept inert")
    if "<script" in json.dumps(payload):
        fail("raw <script> crossed into JSON output")

    digest_path = tmp / "adversarial.md"
    run_extract([str(ADVERSARIAL), "--out", str(digest_path)])
    digest_text = digest_path.read_text(encoding="utf-8")
    if "<script" in digest_text:
        fail("digest reactivated a <script> tag")
    if "javascript:" not in digest_text:
        fail("javascript: note was not preserved as escaped inert text")
    if "IGNORE ALL PREVIOUS INSTRUCTIONS" not in digest_text:
        fail("injection note missing from --out digest")
    ok("adversarial labels stay inert escaped text in JSON and --out")


def check_errors_and_limits(tmp: Path) -> None:
    include = tmp / "include.puml"
    include.write_text(
        "@startuml\n!includeurl https://example.invalid/remote.puml\n"
        "Alice -> Bob : hi\n@enduml\n",
        encoding="utf-8",
    )
    expect_error([str(include)], "include not inlined")

    gantt = tmp / "gantt.puml"
    gantt.write_text("@startgantt\nProject starts 2026-01-01\n@endgantt\n", encoding="utf-8")
    process = invoke([str(gantt)])
    if process.returncode != 2:
        fail(f"@startgantt exited {process.returncode}")
    if SUPPORTED_KINDS not in process.stderr:
        fail(
            "supported-kinds message must list "
            f"{SUPPORTED_KINDS!r} verbatim: {process.stderr!r}"
        )
    if "unsupported diagram kind" not in process.stderr:
        fail("gantt rejection did not name the unsupported kind")

    mixed = tmp / "mixed.puml"
    mixed.write_text(
        "@startuml\nparticipant A\nclass Box\nA -> Box : hi\n@enduml\n",
        encoding="utf-8",
    )
    expect_error([str(mixed)], "mixed or unknown kind")

    malformed = tmp / "malformed.puml"
    malformed.write_text("@startuml\nparticipant A\n???\n@enduml\n", encoding="utf-8")
    expect_error([str(malformed)], "malformed statement at line")

    extractor = load_extractor_module()
    oversize = tmp / "oversize.puml"
    oversize.write_bytes(b"x" * (extractor.MAX_SOURCE_BYTES + 2))
    expect_error([str(oversize)], "4 MiB")

    long_line = tmp / "long-line.puml"
    cap = extractor.MAX_STATEMENT_CHARS
    long_line.write_text(
        "@startuml\nparticipant A\nA -> B : " + ("x" * (cap + 8)) + "\n@enduml\n",
        encoding="utf-8",
    )
    expect_error(
        [str(long_line)],
        f"statement at line 3 exceeds the {cap}-character limit",
    )

    empty = tmp / "empty.puml"
    empty.write_text("@startuml\n@enduml\n", encoding="utf-8")
    expect_error([str(empty)], "mixed or unknown kind")

    state = tmp / "state.puml"
    state.write_text("@startuml\nstate Active\n[*] --> Active\n@enduml\n", encoding="utf-8")
    expect_error([str(state)], "unsupported diagram kind")
    expect_error([str(state)], SUPPORTED_KINDS)

    fenced = tmp / "fenced.md"
    fenced.write_text(
        "# Notes\n\n```plantuml\n@startuml\nAlice -> Bob : ping\n@enduml\n```\n",
        encoding="utf-8",
    )
    payload = json.loads(run_extract([str(fenced), "--json"]))
    if payload["diagrams"][0]["kind"] != "sequence":
        fail("fenced plantuml block was not parsed as sequence")
    if payload["diagrams"][0]["edges"][0]["label"] != "ping":
        fail("fenced plantuml block dropped the message label")

    too_many_nodes = tmp / "nodes.puml"
    too_many_nodes.write_text(
        "@startuml\n"
        + "\n".join(f"participant N{index}" for index in range(extractor.MAX_NODES + 1))
        + "\nN0 -> N1 : ping\n@enduml\n",
        encoding="utf-8",
    )
    expect_error(
        [str(too_many_nodes)],
        f"node limit exceeded (max {extractor.MAX_NODES})",
    )

    too_many_edges = tmp / "edges.puml"
    too_many_edges.write_text(
        "@startuml\nparticipant A\nparticipant B\n"
        + "\n".join("A -> B : ping" for _ in range(extractor.MAX_EDGES + 1))
        + "\n@enduml\n",
        encoding="utf-8",
    )
    expect_error(
        [str(too_many_edges)],
        f"edge limit exceeded (max {extractor.MAX_EDGES})",
    )

    expect_error([str(SEQUENCE), "--diagram", "first"], "--diagram must be an index or 'all'")
    expect_error([str(SEQUENCE), "--max-rows", "0"], "--max-rows must be at least 1")
    ok("all documented exit-2 paths and resource caps fire specifically")


def check_legacy_stdout_encoding(tmp: Path) -> None:
    source = tmp / "unicode-stdout.puml"
    source.write_text(
        '@startuml\nparticipant "登录" as a\nparticipant "résumé" as b\na -> b : 続行 ⇒\n@enduml\n',
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp1252"
    env["PYTHONUTF8"] = "0"
    process = subprocess.run(
        [sys.executable, str(EXTRACT), str(source)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if process.returncode != 0:
        fail(
            "PlantUML extractor failed with legacy stdout encoding: "
            + process.stderr.decode("utf-8", errors="replace").strip()
        )
    try:
        output = process.stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        fail(f"PlantUML extractor did not emit UTF-8 stdout: {error}")
    for needle in ("登录", "続行 ⇒", "résumé"):
        if needle not in output:
            fail(f"UTF-8 PlantUML digest lost {needle!r}: {output!r}")
    if "�" in output:
        fail("UTF-8 PlantUML digest contains a replacement character")
    destination = tmp / "unicode-stdout.md"
    file_process = subprocess.run(
        [sys.executable, str(EXTRACT), str(source), "--out", str(destination)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if file_process.returncode != 0:
        fail("PlantUML --out failed under a legacy Windows encoding")
    file_output = destination.read_text(encoding="utf-8")
    if normalize_newlines(file_output) != normalize_newlines(output):
        fail("PlantUML --out no longer matches its UTF-8 stdout digest")

    class CallerOwnedStdout(io.StringIO):
        def __init__(self) -> None:
            super().__init__()
            self.reconfigured = False

        def reconfigure(self, **_kwargs: object) -> None:
            self.reconfigured = True

    caller_stdout = CallerOwnedStdout()
    extractor = load_extractor_module()
    with contextlib.redirect_stdout(caller_stdout):
        result = extractor.main([str(source)])
    if result != 0 or caller_stdout.reconfigured:
        fail("imported PlantUML main() reconfigured its caller-owned stdout")
    if "登录" not in caller_stdout.getvalue():
        fail("imported PlantUML main() did not write to its caller-owned stdout")
    ok("PlantUML stdout stays lossless UTF-8 under a legacy Windows encoding")


def check_kind_ignores_message_labels(tmp: Path) -> None:
    """Kind comes from arrow form, not from whether a message has a label."""
    mixed = extract_json(
        write_puml(tmp, "kind-class-label.puml", "Base <|-- Child\nChild --> Service : calls")
    )
    edges = [(edge["source"], edge["target"], edge["arrowhead"]) for edge in mixed["edges"]]
    if mixed["kind"] != "class" or edges != [
        ("Child", "Base", "inheritance"),
        ("Child", "Service", "association"),
    ]:
        fail(f"a labeled arrow overrode a class relationship: {mixed['kind']} {edges}")
    plain = extract_json(write_puml(tmp, "kind-seq-unlabeled.puml", "Alice -> Bob"))
    pair = [(edge["source"], edge["target"], edge["label"]) for edge in plain["edges"]]
    if plain["kind"] != "sequence" or pair != [("Alice", "Bob", "")]:
        fail(f"an unlabeled sequence arrow was not a sequence: {plain['kind']} {pair}")
    ok("kind detection uses arrow form, so class relationships win and unlabeled messages count")


def check_forward_package_links(tmp: Path) -> None:
    """A link before its declarations stays on the package classes."""
    forward = "package p {\n  A --> B : uses\n  class A {\n    +id\n  }\n  class B\n}"
    backward = "package p {\n  class A {\n    +id\n  }\n  class B\n  A --> B : uses\n}"

    def shape(name: str, body: str) -> tuple[list, list]:
        diagram = extract_json(write_puml(tmp, name, body))
        nodes = [(node["id"], node["parent"], node["fields"]) for node in diagram["nodes"]]
        edges = [(edge["source"], edge["target"], edge["label"]) for edge in diagram["edges"]]
        return nodes, edges

    fwd, back = shape("fwd-link.puml", forward), shape("back-link.puml", backward)
    if fwd != back or fwd[1] != [("p.A", "p.B", "uses")] or ("A", None, []) in fwd[0]:
        fail(f"forward package link diverged from the declaration-first form: {fwd} vs {back}")
    ok("forward and backward package links attach to the same package classes")


def check_diamond_navigability(tmp: Path) -> None:
    """A diamond with an arrowhead does not collapse into the diamond alone."""
    def rel(name: str, body: str) -> tuple[str, str, str, str]:
        edge = extract_json(write_puml(tmp, name, "class A\nclass B\n" + body))["edges"][0]
        return edge["arrowhead"], edge["source"], edge["target"], edge.get("navigable", "")

    if rel("comp.puml", "A *-- B") == rel("comp-dir.puml", "A *--> B"):
        fail("composition lost the navigability of *-->")
    if rel("agg.puml", "A o-- B") == rel("agg-dir.puml", "A o--> B"):
        fail("aggregation lost the navigability of o-->")
    if rel("comp-dir.puml", "A *--> B") != ("composition", "A", "B", "target"):
        fail(f"*--> did not keep composition and direction: {rel('comp-dir.puml', 'A *--> B')}")
    if rel("comp-rev.puml", "A <--* B") != ("composition", "B", "A", "target"):
        fail(f"<--* did not keep the navigable end: {rel('comp-rev.puml', 'A <--* B')}")
    digest = run_extract([str(write_puml(tmp, "comp-digest.puml", "class A\nclass B\nA *--> B"))])
    if "navigable target" not in digest:
        fail(f"digest dropped navigability: {digest!r}")
    ok("diamond arrows keep navigability apart from the diamond in JSON and the digest")


def check_oversized_dash_line(tmp: Path) -> None:
    """A dash-only line over the statement cap errors before the arrow scan."""
    cap = load_extractor_module().MAX_STATEMENT_CHARS
    source = tmp / "dash-line.puml"
    source.write_text("@startuml\n" + ("-" * (128 * 1024)) + "\n@enduml\n", encoding="utf-8")
    started = time.monotonic()
    expect_error([str(source)], f"statement at line 2 exceeds the {cap}-character limit")
    if time.monotonic() - started > 2.0:
        fail("oversized dash line did not fail before the arrow scan")
    ok("oversized dash lines hit the statement cap before kind detection")


def check_cache_note_example() -> None:
    """The attached cache note stays plain text in the IR, the example, and the row."""
    diagram = json.loads(run_extract([str(SEQUENCE), "--json"]))["diagrams"][0]
    note = next(item for item in diagram["note_details"] if "cache" in item["text"])
    if note["text"] != "keep the cache cold" or note["participants"] != ["api"]:
        fail(f"extractor did not keep the cache note as plain text on api: {note}")
    example = EXAMPLE.read_text(encoding="utf-8")
    if "keep the cache cold" not in example or "<b>cache</b>" in example:
        fail("worked example does not show the cache note as plain text")
    row = next(line for line in IMPORT_REF.read_text(encoding="utf-8").splitlines() if "<b>cache</b>" in line)
    if "keep the cache cold" not in row or "dropped" in row:
        fail(f"fidelity row does not record the kept cache note: {row}")
    ok("attached cache note stays plain text in the IR, the example, and the fidelity row")


def check_docs_and_wiring() -> None:
    import_text = IMPORT_REF.read_text(encoding="utf-8")
    expected_slash_command = f"/diagram-design:{COMMAND.stem}"
    documented_slash_commands = set(
        re.findall(r"`(/diagram-design:[a-z0-9-]+)`", import_text)
    )
    if documented_slash_commands != {expected_slash_command}:
        rendered = ", ".join(sorted(documented_slash_commands)) or "none"
        fail(
            "import-plantuml.md slash command does not match "
            f"{COMMAND.name}: expected {expected_slash_command}, found {rendered}"
        )
    for needle in (
        "plantuml_extract.py",
        "output-spec.md",
        "## Step 1 — Extract the IR",
        "## Step 2 — Set the four dials",
        "## Step 3 — Pick the target type",
        "## Step 4 — Build the semantic model",
        "## Step 5 — Redraw",
        "## Step 6 — Deliver",
        "## Worked example",
        "Multi-block files",
        "## Edge cases",
        "## Anti-patterns",
        "fidelity ledger",
        "untrusted data",
        "never renders, fetches, or executes",
        "--diagram all",
        "example-import-plantuml.html",
        "include not inlined",
        SUPPORTED_KINDS,
    ):
        if needle not in import_text:
            fail(f"import-plantuml.md missing {needle!r}")

    skill_text = SKILL.read_text(encoding="utf-8")
    for needle in (
        "references/import-plantuml.md",
        "plantuml_extract.py",
        ".puml",
        "PlantUML",
    ):
        if needle not in skill_text:
            fail(f"SKILL.md missing PlantUML router text {needle!r}")
    if "PlantUML" not in skill_text.split("---")[1]:
        fail("SKILL.md frontmatter description does not mention PlantUML")
    if "## 11." not in skill_text or "import-plantuml.md" not in skill_text:
        fail("SKILL.md §11 does not name the PlantUML route")

    command_text = COMMAND.read_text(encoding="utf-8")
    reference_flags = (
        "--format",
        "--size",
        "--detail",
        "--audience",
        "--type",
        "--diagram",
        "--variant",
        "--output",
    )
    for flag in reference_flags:
        if flag not in command_text or flag not in import_text:
            fail(f"command/reference flag drift: {flag}")
    if "references/import-plantuml.md" not in command_text:
        fail("command unlinked from references/import-plantuml.md")
    if "references/import-plantuml.md" not in PROMPT.read_text(encoding="utf-8"):
        fail("Pi prompt unlinked from references/import-plantuml.md")
    if "advertised by Pi" not in PROMPT.read_text(encoding="utf-8"):
        fail("Pi prompt does not discover the skill via advertised SKILL.md")

    size_marker = "- `--size` — any preset in `output-spec.md` §2:"
    size_line = next(
        (line for line in command_text.splitlines() if line.startswith(size_marker)),
        "",
    )
    listed = re.findall(r"`([a-z0-9-]+)`", size_line[len(size_marker) :])
    expected = spec_size_presets()
    if listed != expected:
        fail(
            "command --size line must list every output-spec.md §2 preset in order: "
            f"expected {expected}, found {listed}"
        )

    example = EXAMPLE.read_text(encoding="utf-8")
    if 'viewBox="0 0 960 600"' not in example:
        fail("worked example does not use the doc-inline viewBox")
    if example.count("#eb6c36") > 4:
        fail("worked example uses the accent on more than the focal node + legend")
    if '<div class="diagram-container">' not in example or "overflow-x:auto" not in example:
        fail("worked example must contain its wide SVG in a local horizontal scroller")
    lint = subprocess.run(
        [sys.executable, str(ROOT / "scripts/lint-skin.py"), str(EXAMPLE)],
        capture_output=True,
        text=True,
    )
    if lint.returncode != 0:
        fail(f"worked example fails lint-skin: {lint.stdout.strip() or lint.stderr.strip()}")
    ok("reference, SKILL.md, command, prompt, and example stay in sync")


def check_mobile_example() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        ok("worked example has the static mobile-containment contract (browser check runs in lint-render)")
        return
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 390, "height": 844})
        context.route("http*", lambda route: route.abort())
        page = context.new_page()
        page.goto(EXAMPLE.resolve().as_uri(), wait_until="load")
        facts = page.evaluate(
            """
            () => {
              const documentElement = document.documentElement;
              const svg = document.querySelector('svg');
              const scroller = svg && svg.parentElement;
              const overflow = scroller && getComputedStyle(scroller).overflowX;
              return {
                pageOverflow: documentElement.scrollWidth - documentElement.clientWidth,
                svgWidth: svg ? svg.getBoundingClientRect().width : 0,
                localScroller: Boolean(scroller &&
                  (overflow === 'auto' || overflow === 'scroll') &&
                  scroller.scrollWidth > scroller.clientWidth + 1),
              };
            }
            """
        )
        browser.close()
    if facts["pageOverflow"] > 1:
        fail(f"worked example overflows the 390px page by {facts['pageOverflow']:.1f}px")
    if facts["svgWidth"] < 900:
        fail("worked example shrinks its labeled SVG below the 900px legibility floor")
    if not facts["localScroller"]:
        fail("worked example lacks a functioning local horizontal scroller at 390px")
    ok("worked example is contained and locally scrollable at 390px")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="diagram-design-plantuml-") as directory:
        tmp = Path(directory)
        check_files()
        check_sequence()
        check_class()
        check_multi_diagram()
        check_review_regressions(tmp)
        check_kind_ignores_message_labels(tmp)
        check_forward_package_links(tmp)
        check_diamond_navigability(tmp)
        check_oversized_dash_line(tmp)
        check_cache_note_example()
        check_kind_detection_skips_bodies(tmp)
        check_digest_edges_use_ids(tmp)
        check_unselected_comment_isolated(tmp)
        check_generics_survive(tmp)
        check_cardinality_ends(tmp)
        check_note_placement(tmp)
        check_activation_shortcuts(tmp)
        check_whole_arrows(tmp)
        check_command_word_messages(tmp)
        check_activation_keyword_colors(tmp)
        check_together_is_layout_only(tmp)
        check_inline_block_comments(tmp)
        check_quoted_name_cardinality(tmp)
        check_kind_uses_arrow_parser(tmp)
        check_quoted_note_targets(tmp)
        check_endpoint_codes(tmp)
        check_region_boundaries(tmp)
        check_keyword_named_endpoints(tmp)
        check_fences_follow_markdown(tmp)
        check_command_named_kind(tmp)
        check_declaration_styling(tmp)
        check_block_errors_stay_local(tmp)
        check_declaration_edge_forms(tmp)
        check_adversarial(tmp)
        check_errors_and_limits(tmp)
        check_legacy_stdout_encoding(tmp)
        check_detection_matches_parsers(tmp)
        check_docs_and_wiring()
        check_mobile_example()
    print("\nAll PlantUML import gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
