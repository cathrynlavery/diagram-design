# Git graph

**Best for:** branching models, release and hotfix flows, backports, and explaining a rebase versus a merge. Use it when the claim is *what happened on which branch*, with time reading left to right and a merge existing only as a commit that has two parents.

Prefer **Timeline** when events sit on a calendar with no branch topology, **Swimlane** when ownership and handoffs are the claim, **Gantt** when duration and overlap matter, and **Dependency graph** when the story is package fan-in rather than a commit DAG. Git graph has one horizontal lane per branch, a shared column grid for time, and merge semantics that those types cannot draw.

---

## 1. Inputs

```yaml
lanes:                         # 2..5, main/trunk first (top)
  - id: main
  - id: release/1.2
  - id: feat/billing
commits:                       # 4..16, left to right
  - id: c0
    lane: main
    column: 0
  - id: c1
    lane: feat/billing
    column: 1
  - id: c2
    lane: feat/billing
    column: 2
  - id: m1
    lane: main
    column: 3
    merge: [c0, c2]            # exactly two earlier parents on different lanes
  - id: c3
    lane: main
    column: 4                  # later parent of the release cut; not m1
  - id: r0
    lane: release/1.2
    column: 5
  - id: h1
    lane: release/1.2
    column: 6
    focal: true                # hotfix
  - id: r1
    lane: release/1.2
    column: 7
    focal: true                # tagged release
    tag: v1.2.0
  - id: m2
    lane: main
    column: 8
    merge: [c3, r1]            # tagged commit, not a column shared with r1
dark: false
```

Rules:

- `lanes` contains 2–5 entries. Main/trunk is first and draws on top. One lane is a timeline; more than five is two diagrams.
- `commits` contains 4–16 entries on a shared column grid. Fewer than four cannot show a branch-off and a merge; more than sixteen needs an overview plus a zoom.
- A merge commit declares exactly two parents. Both parents sit on earlier columns and on different lanes. A merge drawn as a plain line with no merge commit is a different (wrong) grammar.
- At most two commits are `focal: true`. Typical focals are the hotfix and the tagged release.
- `tag` is optional and names an existing commit. Tags are small outlined labels above that commit, not a fifth lane.

---

## 2. Layout grammar

The canonical `doc-wide` canvas is `1280×720`. All structural coordinates sit on the 4px grid.

```text
outer_x          = 80
lane_label_x     = 88
lane_ys (2–3)    = 240, 380, 520        # 140px pitch
lane_ys (4–5)    = 216, 312, 408, 504, 600   # 96px pitch, the minimum
col_origin       = 280
col_pitch        = 120                  # maximum; shrink for wide graphs (below)
col_x(i)         = col_origin + i * col_pitch
commit_r         = 8
merge_ring_r     = 12
tag_h            = 22
tag_gap          = 28                   # from commit centre up to tag baseline
```

Pick the lane pitch by lane count so every rail stays on the 720px canvas. Extending the 140px pitch past three lanes puts the fifth rail at y=800, off the canvas. With four or five lanes, move the `time →` cue up to y=160 and the legend strip down so its rule sits at y≥648, below the last rail's annotations; drop the legend if it does not fit.

Pick the column pitch from the largest column index so the last commit stays on the canvas: `col_x(max_col)` must be at most 1240. Use `col_pitch = min(120, (1240 - col_origin) / max_col)`, rounded down to the 4px grid. Eight columns keep the 120px pitch; a largest index of fifteen drops it to 64px. The largest index is a limit of its own — with empty columns allowed below, it can exceed the commit count. If tags or merge rings collide at that pitch, split the graph into an overview plus a zoom.

Time reads left to right on the column grid. Every commit sits on its lane's `y` and on `col_x(column)`. Do not nudge a dot “to open space”; the grid is the claim.

### Lanes

- Draw one muted horizontal rail per lane from the first commit on that lane to the last.
- Put the branch name at the lane start (`lane_label_x`), vertically centred on the rail, in `{eyebrow}` / Geist Mono.
- Rails share one muted stroke. Do not colour each lane a different hue.

### Commits

- A commit is a small filled dot at `(col_x(i), lane_y)`.
- A merge commit is the same dot plus a thin outline ring, and it is the only vertex with two incoming connectors.
- Leave most commits unlabelled. Name the merge, the hotfix, or the tag — not every hash.

### Connectors

- On-lane history is a horizontal run along the rail (`M x1,y H x2`).
- A **branch-off** leaves the parent at the parent's column: vertical first, then horizontal on the child lane (`M px,py V cy H cx`). Dropping after a run along the parent rail reads as branching from a column with no commit. The whole path is that elbow — extra corners, a later diagonal, or a second `M` are not a connection.
- A **merge** runs on the source lane and turns into the merge dot at the merge column: horizontal then vertical (`M sx,sy H mx V my`). Rising at the source column and then running along the destination rail is indistinguishable from that rail.
- No connector segment may be collinear with a lane line other than the source or child lane it is drawing. Two connectors may meet at a commit; they must not share a vertical or horizontal run. Cut a release branch from a later main commit than the feature merge so the two verticals do not occupy the same ink.
- Two commits must not share a lane and a column. Two commits must not share a column if a merge would have to pass through the other — move the merge one column later.
- Empty columns are allowed. Column `i` still sits at `col_origin + i × col_pitch`; an unused index does not stretch the gap between occupied dots.
- Bake corners as one continuous `M/H/V/L` path; a slant with an arrowhead is not (SKILL.md §6).
- Connectors never run right-to-left. Parent columns are strictly earlier than the child.
- Paint connectors under the dots. No arrowheads: the grid already says “later”.

### Tags

- One small outlined label above the tagged commit, centred on its column.
- The visible text matches `data-tag` and the bound `data-commit` exists.

---

## 3. Focal and color rules

Coral goes on at most one or two commits, typically the release or the hotfix. Rails, ordinary commits, and connectors stay ink / muted.

Do not assign a rainbow of lane colours. Branch identity is the name at the rail start, not a hue.

---

## 4. Legend

Use a bottom strip when the focal dots need a key. The canonical examples show:

- muted dot — `Commit`
- coral dot — `Hotfix / release`
- outlined chip — `Tag`

If the title already names the tagged release and the coral dots are obvious, drop the legend.

---

## 5. Reproducibility checklist

1. Lane count is 2–5, main on top, rails at least 96px apart, every rail inside the canvas (140px pitch for 2–3 lanes, 96px from y=216 for 4–5).
2. Commit count is 4–16. Every dot sits on its lane `y` and on the shared column grid. Two commits do not share a lane and a column. Unused column indices keep the same pitch.
3. Every merge commit has exactly two incoming connectors from earlier columns on different lanes.
4. A branch is the whole parent-column-then-child-lane elbow. A merge is the whole source-lane-then-merge-column elbow. No second `M`, no later diagonal, no extra corners. No segment runs along a lane it is not drawing. Two connectors do not share a run. No connector runs right-to-left. Elbows are orthogonal, never a marked diagonal.
5. Tags attach to an existing commit. At most two commits wear coral, including fills set by `style` or inherited from an ancestor.
6. Most commits are unlabelled. Lanes are not rainbow-coloured.
7. The SVG uses the accessible SVG contract and the wrapper owns horizontal scrolling.

---

## 6. What `verify-git-graph.py` requires

The checker reads attributes, so every mark binds itself to a lane, a column, and (for connectors and tags) the commits it names.

- **Bindings.** Each commit is a `<circle data-commit>` with `data-lane` and `data-column`. Merge commits also carry `data-kind="merge"`. Each connector is a `<path data-from data-to>` whose `d` is an absolute `M/H/V/L` elbow. Each tag is a `<text data-tag data-commit>`. Each lane has one `<line data-lane data-y>` rail and one `<text data-lane>` label.
- **Geometry.** Every commit `cy` matches its lane `data-y`; every commit `cx` matches its column on one shared pitch (`col_origin + i × pitch`, so unused column indices do not stretch the gap). Two commits must not share a lane and a column. Merge commits have exactly two incoming connectors; those sources are earlier columns on different lanes. Connector endpoints land on the named commits; no `x` in the path decreases. Each connector is one continuous orthogonal `M/H/V/L` elbow — a second moveto or an unsupported command is not a connection. A branch connector's whole route is vertical at the parent column then horizontal on the child lane; a merge connector's whole route is horizontal on the source lane then vertical at the merge column. A horizontal segment may sit on the lane it is drawing, not on another rail. Two connectors may meet at a commit, not share a segment. A connector touches no commit dot other than the two it names. Tags sit above the commit they name. Lanes do not overlap, and every lane rail sits inside the root `viewBox` height with room for a commit radius. At most two commit fills are the accent, read from the `fill` attribute, an inline `style`, or the nearest ancestor.
- **Unpositioned geometry.** Coordinates are raw attributes. A `transform`, an inline `style` that moves a mark, or a `<style>` rule with `transform` / geometry properties is a finding. Bound marks that are hidden (display, visibility, zero opacity) still count, so they fail rather than pass quietly — including a `<style>` rule that hides a bound mark or its parent. A connector with no visible stroke (`stroke="none"`, a transparent color, or `stroke-width="0"`, set inline or inherited) is hidden too and fails, as does a commit dot with no visible paint (`fill="none"` or transparent and no visible stroke).
- **Vocabulary treaty.** `data-commit` on a `<circle>` is this contract. `data-value` (beeswarm), `data-q1` (box plot), `data-span` (arc diagram), `data-size` (bubble), `data-series` (slopegraph), and `data-ranks` (bump) are never bound here.

A minimal four-commit figure that passes:

```html
<svg viewBox="0 0 1280 720" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="git-graph-min-title git-graph-min-desc">
  <title id="git-graph-min-title">Feature merge on main</title>
  <desc id="git-graph-min-desc">Main on top; a feature branch merges back at the coral commit.</desc>
  <rect width="100%" height="100%" fill="#f5f5f5"/>
  <line data-lane="main" data-y="240" x1="280" y1="240" x2="640" y2="240" stroke="#4f5d75"/>
  <line data-lane="feat" data-y="380" x1="400" y1="380" x2="520" y2="380" stroke="#4f5d75"/>
  <path data-from="c0" data-to="m1" d="M 280,240 H 640" fill="none" stroke="#4f5d75"/>
  <path data-from="c0" data-to="c1" d="M 280,240 V 380 H 400" fill="none" stroke="#4f5d75"/>
  <path data-from="c1" data-to="c2" d="M 400,380 H 520" fill="none" stroke="#4f5d75"/>
  <path data-from="c2" data-to="m1" d="M 520,380 H 640 V 240" fill="none" stroke="#4f5d75"/>
  <circle data-commit="c0" data-lane="main" data-column="0" cx="280" cy="240" r="8" fill="#2d3142"/>
  <circle data-commit="c1" data-lane="feat" data-column="1" cx="400" cy="380" r="8" fill="#2d3142"/>
  <circle data-commit="c2" data-lane="feat" data-column="2" cx="520" cy="380" r="8" fill="#2d3142"/>
  <circle data-commit="m1" data-lane="main" data-column="3" data-kind="merge" cx="640" cy="240" r="8" fill="#bf4520"/>
  <text data-lane="main" x="88" y="244">main</text>
  <text data-lane="feat" x="88" y="384">feat</text>
  <text data-tag="v1" data-commit="m1" x="640" y="212">v1</text>
</svg>
```

---

## 7. Anti-patterns

- Labelling every commit. The grid already orders them; extra hashes become noise.
- Rainbow lane colours. Branch names at the rail start carry identity.
- Crossing connectors, a connector that runs right-to-left, a connector that runs along a lane it is not drawing, or a feature merge and a release cut that share a vertical.
- Drawing a merge as a plain line with no merge commit (two parents must meet at a dot).
- Using Timeline or Swimlane for a branching model, a release cut, a hotfix backport, or rebase-versus-merge.
- More than two coral commits, or coral on a whole lane.

## Examples

- `assets/example-git-graph.html` — minimal light.
- `assets/example-git-graph-dark.html` — minimal dark with the same topology.
- `assets/example-git-graph-full.html` — full editorial with unchanged geometry.
