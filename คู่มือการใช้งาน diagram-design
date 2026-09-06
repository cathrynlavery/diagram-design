# คู่มือการใช้งาน `diagram-design`

คู่มือนี้สรุปวิธีสั่งงาน Diagram Design สำหรับสร้าง แก้ไข นำเข้า ตรวจสอบ และส่งออกไดอะแกรม โดยอ้างอิง `diagram-design` skill รุ่น 2.6

> ใช้งานได้ทั้งการพิมพ์เป็นภาษาธรรมชาติ และ slash command หากปลั๊กอินของสภาพแวดล้อมนั้นเปิดใช้งานไว้

## 1. เริ่มต้นแบบเร็วที่สุด

ใช้รูปแบบนี้เมื่อสร้างไดอะแกรมใหม่:

```text
ใช้ diagram-design สร้าง [ประเภทไดอะแกรม]
หัวข้อ: [สิ่งที่ต้องการสื่อ]
ข้อมูล/โหนด: [รายการข้อมูล]
ความสัมพันธ์หรือขั้นตอน: [รายการลูกศร/ลำดับ]
ผู้ชม: [engineer | mixed | executive]
ขนาด: [doc-inline | doc-wide | slide-16x9 | social-og | ...]
รูปแบบ: [html | svg | png | html+png]
สไตล์: [minimal light | minimal dark | full editorial]
ชื่อไฟล์: [ชื่อไฟล์]
```

ตัวอย่าง:

```text
ใช้ diagram-design สร้าง architecture diagram สำหรับระบบอนุมัติ CAPEX
โหนด: ผู้ขอ, CAPEX Portal, Workflow, Finance, Approver, ERP
ความสัมพันธ์: ผู้ขอส่งคำขอ → Portal → Workflow ตรวจสอบ → Finance/Approver → ERP
ผู้ชม: mixed
ขนาด: slide-16x9
รูปแบบ: html
ชื่อไฟล์: capex-approval-architecture.html
```

ถ้าไม่ได้ระบุค่า จะใช้ค่าเริ่มต้น: `html`, `doc-inline`, `balanced`, `mixed`, `minimal light`, แบบ static ไม่มี animation

## 2. กฎการเลือกไดอะแกรม

เลือก semantic pattern ก่อนเมื่อพฤติกรรม สถานะ การบังคับใช้ หรือความเสี่ยงเป็นสาระสำคัญ จากนั้นเลือก visual type ที่เหมาะสม

| ต้องการสื่อ | Semantic pattern | ประเภทที่เหมาะสม |
|---|---|---|
| หลายแหล่งแย่งทรัพยากรที่มีความจุจำกัด | Fan-in queue / bottleneck | Data flow |
| แต่ละ stage มี Question/Input/Governance/Output ซ้ำกัน | Stage framework with semantic slots | Process |
| บทสนทนาหรือข้อมูลดิบกลายเป็นเอกสาร/record | Unstructured input → structured artifact | Data flow |
| เปรียบเทียบกฎ 2 trace และจุดแตกต่างแรก | Paired policy-evaluation traces | Flowchart |
| Trust boundary, route ที่อนุญาตและถูกบล็อก | Secure paved road | Architecture |
| Controls แบ่งตามจุดที่บังคับใช้ | Governance / control catalog | Layer stack |
| การป้องกันหลายชั้นและ residual risk | Compensating security layers | Layer stack |

ข้อจำกัดของ pattern ต้องใช้ร่วมกับข้อจำกัดของ visual type และใช้ข้อที่เข้มงวดกว่า หากเกินงบให้แยกเป็น overview + detail

## 3. รายการ visual type ทั้งหมด

| ประเภท | ใช้เมื่อ |
|---|---|
| `architecture` | components และ connections ของระบบ |
| `it-state` | ภาพ IT landscape เดิม แบ่งตาม phase/department |
| `flowchart` | decision logic และ branching |
| `sequence` | message ตามลำดับเวลาระหว่าง actors |
| `state` | states, transitions, guards |
| `er` | entities, fields, relationships |
| `timeline` | events บนแกนเวลา |
| `swimlane` | process ข้ามทีม/เจ้าของงาน |
| `quadrant` | การวางตำแหน่งบน 2 แกน |
| `radar` / `spider` | หลาย entity เทียบ 3–5 criteria |
| `polar` | series เดียวบนหมวดหมู่แบบวงรอบ |
| `loop` | reinforcing cycle / flywheel |
| `nested` | hierarchy ผ่าน containment/scope |
| `tree` | parent → children |
| `org-chart` | reporting, ownership, routing, escalation |
| `layers` | abstraction levels แบบซ้อนชั้น |
| `venn` | overlap ของ sets |
| `pyramid` / `funnel` | ranked hierarchy หรือ conversion drop-off |
| `bar` | เปรียบเทียบค่าระหว่าง categories |
| `treemap` | part-of-whole ที่ขนาดสัมพันธ์กัน |
| `line` | trend, slopegraph, ridgeline หรือ bump chart |
| `gantt` | tasks/phases บน timeline |
| `scatter` | distribution/correlation, bubble หรือ beeswarm |
| `high-level` | data stack ระดับ end-to-end |
| `process` | sequential process หลาย actor พร้อม data handoff |
| `medallion` | data storage หลายระดับคุณภาพ/สิทธิ์ |
| `data-flow` | ใครทำอะไรในแต่ละ pipeline step |
| `dp-integration` | data platform: sources → core → consumers |
| `dp-security-matrix` | สิทธิ์ของ role/component ต่อ resource |
| `sankey` | ปริมาณแยก/รวม โดยความหนาของ band = จำนวน |
| `fishbone` | root-cause analysis |
| `wardley` | value chain เทียบกับ evolution |
| `kanban` | งานตาม state, WIP limit, blocked items |
| `journey` | สิ่งที่ผู้ใช้ทำและความรู้สึกตาม stages |
| `deployment` | zones, hosts, artifacts, replicas, ports |
| `dependency` | dependency, fan-in และ cycle |
| `uml-class` | classes, operations, inheritance, composition |
| `story-map` | narrative, releases และ cut line |
| `db-schema` | physical tables, SQL types, indexes, column FKs |

สำหรับรายละเอียด layout ของแต่ละประเภท ให้เปิดไฟล์ `references/type-<ชื่อ>.md` ในโฟลเดอร์ skill

## 4. ตัวเลือกผลลัพธ์ 4 แกน

### Format

| ค่า | ผลลัพธ์ |
|---|---|
| `html` | self-contained HTML เป็นค่าเริ่มต้น |
| `svg` | SVG ของตัวไดอะแกรมเท่านั้น |
| `png` | PNG พื้นหลังโปร่งใส |
| `html+png` | HTML และ PNG |

สร้าง HTML ก่อนเสมอ แล้วค่อย export SVG/PNG เมื่อผู้ใช้ขออย่างชัดเจน

### Size

| ค่า | viewBox | ใช้สำหรับ |
|---|---|---|
| `doc-inline` | `960×600` | README, blog, เอกสารแทรกในเนื้อหา |
| `doc-wide` | `1280×720` | wiki หรือเอกสารเต็มความกว้าง |
| `slide-16x9` | `1280×720` | PowerPoint/Keynote/Google Slides |
| `slide-4x3` | `1024×768` | deck แบบเก่า |
| `social-og` | `1200×632` | link preview / OG card |
| `social-square` | `1080×1080` | social post แบบสี่เหลี่ยม |
| `print-a4-landscape` | `1120×792` | A4 แนวนอน |
| `print-letter-landscape` | `1056×816` | US Letter แนวนอน |
| `fit` | คำนวณจากเนื้อหา | vector hand-off |

เว้นขอบอย่างน้อย 40px; `social-og` เว้น 64px และกันพื้นที่ legend ด้านล่าง 60px

### Detail

| ค่า | เพดานโดยประมาณ | ลักษณะ |
|---|---:|---|
| `faithful` | 24 nodes / 32 edges | เก็บองค์ประกอบเกือบทั้งหมด ต้องแบ่งเป็น zones เมื่อเกิน 9 nodes |
| `balanced` | 12 nodes / 16 edges | ค่าเริ่มต้น รวม leaf clusters ได้ |
| `simplified` | 7 nodes / 9 edges | เหลือเฉพาะ capability และลำดับหลัก |

ลำดับการลดรายละเอียด: decorative cells → duplicates → leaf clusters → degree-1 sinks → cross-cutting infrastructure → แยกเป็นหลายภาพ

### Audience

| ค่า | การตั้งชื่อ |
|---|---|
| `engineer` | ชื่อ service จริง, protocol, port, version |
| `mixed` | ชื่อ component อ่านง่าย และมี technology เฉพาะที่ช่วยตัดสินใจ |
| `executive` | capability/outcome และ business verbs; ตัด vendor/protocol/infrastructure |

## 5. คำสั่งนำเข้า draw.io

ใช้เมื่อมีไฟล์ `.drawio`, `.drawio.xml`, `.drawio.png` หรือ `.drawio.svg`:

```text
ใช้ diagram-design import draw.io จาก "C:\path\to\system.drawio"
ทำเป็น architecture diagram สำหรับ slide-16x9
detail: balanced, audience: mixed, format: html
```

Slash command ที่สกิลระบุ:

```text
/diagram-design:import-drawio "C:\path\to\system.drawio"
```

คำสั่ง extract โครงสร้างก่อน redraw:

```powershell
python3 "<skill-dir>\scripts\drawio_extract.py" "<file.drawio>"
python3 "<skill-dir>\scripts\drawio_extract.py" "<file.drawio>" --page all
python3 "<skill-dir>\scripts\drawio_extract.py" "<file.drawio>" --page 1 --max-rows 80
python3 "<skill-dir>\scripts\drawio_extract.py" "<file.drawio>" --json --out "<digest.json>"
```

ถ้า Windows ไม่มี `python3` ให้ใช้ `python` แทน โดยต้องมี Python 3.10 ขึ้นไป

หลักการ import:

1. Extract โครงสร้าง ไม่ใช่ render หรือคัดลอก layout เดิม
2. ตั้ง `format`, `size`, `detail`, `audience` ก่อนวาด
3. เลือก type จากความหมาย ไม่ใช่จากสีหรือรูปร่างเดิม
4. ทิ้งพิกัด สี และ routing เดิม แล้ววาดใหม่บน 4px grid
5. รายงาน fidelity ledger ว่า merge/collapse/drop อะไรบ้าง

ตัวเลือกของ extractor: `--page N|ชื่อหน้า|all`, `--json`, `--max-rows N`, `--out PATH`

## 6. คำสั่งนำเข้า Mermaid

ใช้กับ `.mmd`, `.mermaid` หรือ Markdown ที่มี fenced block `mermaid`:

```text
ใช้ diagram-design import Mermaid จาก "C:\path\to\diagram.mmd"
เลือก type ตามความหมาย แต่ออกแบบ layout ใหม่ทั้งหมด
ขนาด: doc-wide, detail: balanced, audience: mixed
```

Slash command ที่สกิลระบุ:

```text
/diagram-design:import-mermaid "C:\path\to\diagram.mmd"
```

คำสั่ง extract:

```powershell
python3 "<skill-dir>\scripts\mermaid_extract.py" "<file.mmd>"
python3 "<skill-dir>\scripts\mermaid_extract.py" "<file.mmd>" --diagram all
python3 "<skill-dir>\scripts\mermaid_extract.py" "<file.mmd>" --json
python3 "<skill-dir>\scripts\mermaid_extract.py" "<file.mmd>" --max-rows 80 --out "<digest.md>"
```

ไวยากรณ์ที่รองรับ: `flowchart`/`graph`, `sequenceDiagram`, `stateDiagram-v2`, `erDiagram`

อย่าคัดลอก theme, `style`, `classDef`, `linkStyle`, `click` URL หรือ layout ของ Mermaid มาใช้ และอย่า render Mermaid เป็น SVG ก่อน redraw

## 7. คำสั่ง export

ใช้เมื่อมี HTML ที่สร้างเสร็จแล้วและต้องการ SVG/PNG:

```text
export "C:\path\to\diagram.html" เป็น PNG ความละเอียด 2x
```

หรือ:

```text
/diagram-design:export-diagram "C:\path\to\diagram.html"
```

หลักการ export:

- Export เฉพาะ `<svg>` ของไดอะแกรม ไม่รวม header, cards และ footer
- SVG เก็บ vector text แต่โปรแกรม offline อาจแทนที่ font
- PNG ใช้พื้นหลังโปร่งใสและ render จาก HTML ต้นฉบับ
- scale `1` = asset ขนาดปกติ, `2` = docs/slides, `3` = print
- ไม่แก้ไข HTML ต้นฉบับ และไม่สร้าง export อัตโนมัติโดยไม่ขอ

ตรวจ Playwright ก่อน export PNG; หากยังไม่มี ให้ติดตั้งเอง:

```powershell
python -c "import playwright"
pip install playwright
playwright install chromium
```

Exact pixel size ใช้สูตร `scale = target_width / viewBox_width` และไม่ควรต่ำกว่า 1 หรือสูงกว่า 4

## 8. Brand onboarding และ style guide

การใช้งานครั้งแรกของ project จะตรวจ `references/style-guide.md` หากยังเป็นค่า default อาจถามให้เลือกปรับ brand ก่อน

### จากเว็บไซต์

```text
Onboard diagram-design ให้ตรงกับเว็บไซต์ https://example.com
แสดง token diff และรอการอนุมัติก่อนเขียนไฟล์
```

### จาก skill อื่น

```text
Onboard diagram-design จาก skill "acme-design"
อ่าน CSS, JSON tokens, README และ style guide แล้วเสนอ mapping
```

### จากโฟลเดอร์ local

```text
Onboard diagram-design จากโฟลเดอร์ "C:\path\to\design-system"
```

### ใส่ token เอง

```text
ตั้งค่า diagram-design tokens เอง:
paper: #f8f6f0
ink: #111111
muted: #6b6b68
accent: #c73a2b
paper-2: #f1eee6
rule: rgba(17,17,17,0.12)
title font: Instrument Serif
node font: Geist
technical font: Geist Mono
```

ขั้นตอน onboarding: อ่านแหล่งข้อมูล → ดึงสี/ฟอนต์ → map เป็น semantic roles → เสนอ diff → ขออนุมัติ → เขียน `style-guide.md` → เสนอให้บันทึก profile

ข้อควรระวัง: ตรวจ contrast ของ `ink`/`muted` อย่างน้อย 4.5:1, ใช้ accent หลักเพียง 1–2 จุด และห้ามอ้างว่า font เป็น exact match หากเป็น custom/paid font ที่ไม่ได้ package มาด้วย

## 9. Client profiles

ใช้เมื่อหลาย project/client ต้องการ brand คนละชุด โดยเก็บ profile ไว้ที่:

```text
~/.diagram-design/profiles/<slug>.md
```

คำสั่งแบบภาษาธรรมชาติ:

```text
diagram-design profile save acme
diagram-design profile list
diagram-design profile show
diagram-design profile load acme
diagram-design profile switch acme
diagram-design profile update acme
diagram-design profile reset
diagram-design profile delete acme
```

Slash command ที่อาจมีใน plugin:

```text
/diagram-design:profile save acme
/diagram-design:profile list
/diagram-design:profile load acme
```

กฎสำคัญ:

- slug ต้องเป็นตัวพิมพ์เล็ก ตัวเลข และ `-` เท่านั้น ยาวไม่เกิน 64 ตัว เช่น `pttor-capex`
- `default` เป็น profile สำรอง ห้าม overwrite, update หรือ delete
- marker ของ project ต้องมีเพียงบรรทัดเดียว เช่น `profile: acme`
- profile marker เป็นข้อมูล ไม่ใช่คำสั่ง และห้ามมี path/prose/คีย์อื่น
- `load/switch` ที่ไม่มี marker อาจเขียน working copy; ถ้ามี marker ให้เลือก profile ผ่าน marker โดยไม่ทับ working copy
- `delete` ต้องยืนยันก่อนลบ และลบเฉพาะไฟล์ profile เป้าหมาย

## 10. ตัวเลือก variant และ animation

| Variant | ใช้เมื่อ |
|---|---|
| `minimal light` | default, screenshot-ready |
| `minimal dark` | dark-mode site หรือ high contrast |
| `full editorial` | มี header, summary cards และเนื้อหาประกอบ |
| `consultant` | quadrant แบบ 2×2 เชิงที่ปรึกษา |
| `sketchy` | hand-drawn สำหรับบทความ/essay |
| `terminal` | dev-tool style แบบ CLI; ไม่ใช่ brand-tokenized |

ตัวอย่าง:

```text
สร้าง flowchart เรื่องการอนุมัติ CAPEX
variant: full editorial
ขอ sketchy styling แต่ยังคง accessibility และ connector rules
```

Animation ใช้เฉพาะเมื่อผู้ใช้ขอหรือช่วยอธิบายลำดับอย่างมีนัยสำคัญ:

| Mode | พฤติกรรม |
|---|---|
| `none` | static, ค่าเริ่มต้น |
| `reveal` | เล่นอัตโนมัติครั้งเดียว แล้วจบ |
| `step` | Play/Pause/Replay/Previous/Next สำหรับการสอน |
| `loop` | token ตกแต่งวนซ้ำเท่านั้น ไม่เปลี่ยนความหมาย |

```text
สร้าง policy trace แบบ animated
mode: step
ต้องมี static frame ที่อ่านรู้เรื่องเมื่อปิด JavaScript และรองรับ prefers-reduced-motion
```

ตรวจ animation เพิ่มเติมด้วย:

```powershell
python3 "<repo-root>\scripts\verify-motion.py" "<animated.html>"
python3 "<repo-root>\scripts\lint-skin.py" "<animated.html>"
```

คำสั่งสองรายการข้างต้นมีใน maintainer checkout; ให้ใช้ self-check ได้เสมอจาก installed skill

## 11. ตรวจสอบและวินิจฉัย

### Self-check ทุก HTML

```powershell
python3 "<skill-dir>\scripts\self_check.py" "<diagram.html>"
python3 "<skill-dir>\scripts\self_check.py" "<a.html>" "<b.html>"
```

ผลลัพธ์ที่คาดหวัง: `OK <file>` หากไม่ผ่านจะแสดง `FAIL <file>` พร้อมรายการปัญหา

### Doctor

```text
รัน diagram-design doctor แบบอ่านอย่างเดียว
```

หรือ:

```text
/diagram-design:doctor
/diagram-design:doctor --strict
/diagram-design:doctor --json
```

Doctor ตรวจ Python ≥3.10, Playwright/Chromium, path และ wiring ที่เกี่ยวข้อง โดยไม่แก้ไฟล์และไม่ติดตั้ง dependency

### Geometry verification

ใน maintainer checkout สามารถตรวจ geometry เพิ่มได้:

```powershell
python3 "<repo-root>\scripts\verify-geometry.py" "<diagram.html>"
```

## 12. Checklist ก่อนส่งมอบ

- เลือก type และ semantic pattern ถูกต้อง
- ระบุหรืออนุมาน `format`, `size`, `detail`, `audience` แล้ว
- อยู่ใน complexity budget; ถ้าเกินให้ split
- ใช้ 4px grid กับพิกัด ขนาด ช่องว่าง และ font ที่เกี่ยวข้อง
- accent ไม่เกิน 2 องค์ประกอบ
- ลูกศร off-axis เป็น rounded orthogonal elbow; ห้ามเส้นทแยง
- label ของลูกศรมี opaque mask และเว้นจากเส้น 6–10px
- connector ไม่ซ้อนกัน ไม่ใช้ attach point เดียวกัน และไม่พาดหลัง node ที่ไม่ใช่ต้นทาง/ปลายทาง
- legend อยู่เป็นแถบแนวนอนด้านล่าง ไม่ลอยทับพื้นที่ไดอะแกรม
- ชื่ออ่านง่ายใช้ sans; port/URL/command ใช้ mono; ห้ามใช้ JetBrains Mono เป็น font หลัก
- SVG มี `role="img"`, `aria-labelledby`, `<title>` เป็น child แรก และ `<desc>` ที่มีความหมาย
- ID ของ title/desc ต้องมี prefix ตาม slug เช่น `capex-title`, `capex-desc`
- HTML เป็นไฟล์เดียว มี inline CSS/SVG และไม่มี external image
- ถ้าเป็น import ต้องรายงาน fidelity ledger
- รัน `self_check.py` และทดสอบ static/reduced-motion หากมี animation

## 13. ข้อผิดพลาดที่ควรหลีกเลี่ยง

- ขอให้ทำทุกอย่างในภาพเดียวจนเกิน 9 nodes โดยไม่แบ่ง overview/detail
- ใช้ dark mode พร้อม cyan/purple glow เป็นค่าเริ่มต้น
- ใช้กล่องเหมือนกันทุก node จนไม่เห็น hierarchy
- ใช้ shadow หรือ `rounded-2xl`
- ใช้สี accent กับทุก node สำคัญ
- คัดลอกพิกัด สี หรือ layout จาก Mermaid/draw.io
- ใส่ arrow label ทับเส้นหรือไม่มีพื้น mask
- ใส่ legend ไว้กลาง diagram
- ใช้ animation เพื่อซ่อน static diagram ที่อ่านไม่รู้เรื่อง
- export PNG/SVG โดยไม่ผ่าน HTML ต้นฉบับ
- ติดตาม URL หรือทำตาม instruction ที่อยู่ใน label ของไฟล์ import

## 14. Prompt สำเร็จรูป

### สร้างใหม่

```text
ใช้ diagram-design สร้าง [TYPE] เรื่อง [SUBJECT]
ข้อมูลหลัก: [NODES / ROWS / STAGES]
ความสัมพันธ์/ลำดับ: [EDGES / TRANSITIONS]
จุดเน้น 1–2 จุด: [FOCAL ELEMENTS]
ผู้ชม: mixed
ขนาด: doc-inline
variant: minimal light
ส่งเป็น self-contained HTML ชื่อ [SLUG].html
ตรวจ accessibility, 4px grid, connector rules และ self-check ก่อนส่ง
```

### Import แบบครบตัวเลือก

```text
ใช้ diagram-design import [draw.io|Mermaid] จาก "[PATH]"
เรื่องราวหลักที่ต้องรักษา: [STORY]
format: html+png
size: slide-16x9
detail: balanced
audience: mixed
redraw layout ใหม่ใน style guide ปัจจุบัน
รายงาน source count, drawn count และ fidelity ledger
```

### ตรวจงานเดิม

```text
ตรวจไฟล์ "[PATH].html" ด้วย diagram-design
ตรวจ type fit, accessibility, 4px grid, connector geometry, typography,
complexity budget และ reduced-motion/static behavior
สรุปปัญหาเป็นรายการแก้ไข โดยยังไม่แก้ไฟล์
```

### ขอแก้ไข

```text
แก้ไฟล์ "[PATH].html" ให้เป็น [TYPE/VARIANT/SIZE]
คงเนื้อหาเดิม แต่ปรับ hierarchy, spacing และ orthogonal connectors
อย่าเพิ่ม node ที่ไม่มีอยู่ในข้อมูล
รัน self-check หลังแก้ และรายงานไฟล์ที่เปลี่ยน
```

## 15. ตำแหน่งไฟล์อ้างอิง

โดยปกติ skill อยู่ที่:

```text
C:\Users\620116\.codex\skills\diagram-design\
```

ไฟล์สำคัญ:

```text
SKILL.md
references\style-guide.md
references\semantic-patterns.md
references\output-spec.md
references\onboarding.md
references\profiles.md
references\import-drawio.md
references\import-mermaid.md
references\export.md
references\doctor.md
references\animation.md
references\type-<ชื่อไดอะแกรม>.md
assets\template.html
assets\template-dark.html
assets\template-full.html
assets\template-motion.html
assets\template-terminal.html
scripts\drawio_extract.py
scripts\mermaid_extract.py
scripts\self_check.py
```

ถ้าคำสั่ง slash ไม่ทำงาน ให้ใช้ prompt ภาษาธรรมชาติในคู่มือนี้แทน และระบุ path ของไฟล์ให้ชัดเจน
