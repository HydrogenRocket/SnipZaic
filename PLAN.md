# SnipZaic — Collage Making App: Development Plan

## What Is This

A desktop app for creating collages and mosaics. The window is split in two:
- **Left**: embedded web browser — browse the web normally
- **Right**: workplane — a canvas representing a physical page (A4, A3, A2, etc.)

The core workflow: use snipping tools on the browser side to cut out shapes, which land on the workplane as layered, moveable objects.

**Core design philosophy**: All material must come from the browser. There is no "import image from disk" feature. Like a traditional collage artist cutting from magazines, the user must find what they need on the web — if you need blue, find a blue page. This is a deliberate creative constraint, not a missing feature.

---

## Tech Stack (Decided)

| Concern | Choice | Reason |
|---|---|---|
| Language | Python | User's primary language |
| UI Framework | **PyQt6** | Cross-platform; QWebEngineView works on Windows |
| Browser embed | **QWebEngineView** | Chromium-based, Linux + Windows |
| Canvas rendering | **QPainter** | Native Qt, no extra deps |
| Windows binary | **PyInstaller** | Well-supported with PyQt6 |
| Linux package | AppImage or .deb | TBD |

---

## Application Architecture

```
SnipZaic/
├── main.py                    # Entry point
├── ui/
│   ├── main_window.py         # Top-level split-pane window
│   ├── browser_panel.py       # Left pane: browser + browser toolbar + snip tray
│   └── workplane_panel.py     # Right pane: canvas + page tools toolbar
├── core/
│   ├── snip.py                # Snip data model (pixmap, mask, transform, effects)
│   ├── project.py             # Project state (page size, snip list, undo stack)
│   └── snip_capture.py        # Capture region from browser view + apply mask
├── tools/
│   ├── browser_tools.py       # Rectangle, polygon, freehand selection overlays
│   └── page_tools.py          # Move, trim, rotate, scale, layer reorder
└── export/
    └── export.py              # Render workplane to PNG/PDF
```

---

## Feature Breakdown

### Browser Panel (Left)

Full embedded Chromium browser via `QWebEngineView`. User browses normally. A quick search bar at the top lets users hunt for colours/textures quickly. When a snip tool is active, a transparent overlay is drawn on top of the browser to capture the selection.

**No image import from disk — all material comes from the browser.**

**Browser Toolbar:**
- URL bar with back / forward / reload
- Quick search bar (opens a web search directly)
- Zoom in/out on the browser view (useful before snipping fine detail)
- Snip tool selector

**Browser Tools:**

| Tool | Description | Interaction |
|---|---|---|
| Rectangle Snip | Cut a rectangular region | Click and drag |
| Polygon Snip | Cut a freeform shape with straight-line segments | Click points, double-click/Enter to close |
| Freehand Snip | Cut by drawing freely | Click and drag, shape follows cursor |

**Snip Capture Workflow:**
1. User activates snip tool → transparent overlay appears on browser
2. User draws selection
3. `QWebEngineView` renders page to pixmap (off-screen render)
4. Crop to bounding box of selection
5. Apply mask for non-rectangular shapes (QPainterPath → alpha mask)
6. Create `Snip` object → added to Snip Tray and to `Project`
7. Snip appears on workplane at a default position

**Snip Tray:**
- A strip (below or beside the browser) showing thumbnails of all snips cut so far
- Drag from tray → drops a fresh copy onto the workplane
- Right-click a tray item → delete from tray
- Persisted with the project so you can re-use snips across sessions

---

### Workplane Panel (Right)

A canvas widget rendered with QPainter. The page is shown against a neutral grey background with a drop shadow to read as a physical sheet.

**Page Sizes (screen: 96 DPI, export: 300 DPI):**
- A4: 210 × 297 mm
- A3: 297 × 420 mm
- A2: 420 × 594 mm
- Custom (width × height in mm)

**Page Tools:**

| Tool | Description |
|---|---|
| Auto | Context-sensitive: hover snip → move, near edge → trim, corner handle → scale/rotate |
| Move Snip | Click and drag to reposition |
| Rotate Snip | Drag rotation handle around a selected snip |
| Scale Snip | Drag corner handles to resize (hold Shift = proportional) |
| Flip | Flip selected snip horizontally or vertically |
| Trim Snip | Draw a straight cut line across a snip; removes one side |
| Layer Up/Down | Drag snip up/down in Z-stack, or use buttons in toolbar |
| Duplicate Snip | Copy a snip on the workplane without re-cutting from browser |
| Lock Snip | Pin position so it can't be accidentally moved |
| Delete Snip | Remove from workplane (stays in Snip Tray) |

**Snip Properties (sidebar or floating panel):**
- Blend mode (Normal, Multiply, Screen, Overlay, Darken, Lighten)
- Drop shadow (toggle + offset + blur + colour)
- Rough/torn edge effect (toggle + intensity — simulates torn paper)

**Workplane View Controls:**
- Zoom in/out (Ctrl+scroll or toolbar buttons)
- Pan (middle-click drag, or Space+drag)
- Fit page to window
- Ruler + grid overlay (toggle; snap to grid optional)
- Page background colour (default white; user can set to any colour)

---

### Snip Data Model

Each snip stores:
- `source_pixmap` — full captured bitmap (never discarded — non-destructive)
- `mask_path` — QPainterPath defining the visible region
- `position` — (x, y) on workplane in mm
- `rotation` — degrees
- `scale` — (sx, sy)
- `flipped_h`, `flipped_v` — booleans
- `opacity` — 0.0–1.0
- `blend_mode` — enum
- `effects` — dict (shadow, torn edge settings)
- `locked` — bool
- `z_index` — int (position in stack)

Snips are non-destructive: all transforms and effects are applied at render time. The original captured pixels are always preserved.

---

## Project Format

A `.snipzaic` file is a ZIP archive containing:
- `project.json` — metadata (page size, page bg colour, snip list with all properties)
- `snips/` — individual snip source images as PNG (named by UUID)

---

## Export

- **PNG** — flat render at chosen DPI (screen 96 or print 300)
- **PDF** — page-sized PDF with embedded raster snips

---

## Build & Distribution

### Linux
- Run directly: `python main.py`
- Package as `.AppImage`

### Windows
- `PyInstaller` → single `.exe` or folder
- `QWebEngineView` ships Qt's Chromium — fully self-contained

---

## Phased Implementation

### Phase 1 — Shell & Layout
- [ ] Main window with resizable split pane (browser left, workplane right)
- [ ] Browser panel: QWebEngineView + URL bar + back/forward/reload
- [ ] Quick search bar in browser panel
- [ ] Workplane panel: QPainter canvas with page rendered + zoom/pan
- [ ] Page size selection (new project dialog)

### Phase 2 — Rectangle Snip (End-to-End)
- [ ] Transparent overlay widget on browser view
- [ ] Rectangle selection tool (click + drag)
- [ ] Browser pixmap capture + crop
- [ ] Snip appears on workplane (moveable)
- [ ] Snip Tray with thumbnail

### Phase 3 — Polygon & Freehand Snip
- [ ] Polygon selection (click points, close on double-click)
- [ ] Freehand selection (mouse draw)
- [ ] Mask generation (QPainterPath → alpha)

### Phase 4 — Page Tools
- [ ] Move snip
- [ ] Rotate + scale handles
- [ ] Flip horizontal/vertical
- [ ] Layer up/down
- [ ] Duplicate snip
- [ ] Lock snip
- [ ] Auto tool (context-sensitive cursor switching)

### Phase 5 — Trim Tool
- [ ] Draw straight cut line across selected snip
- [ ] Split mask along that line, discard one side

### Phase 6 — Snip Effects
- [ ] Opacity slider
- [ ] Blend modes
- [ ] Drop shadow
- [ ] Rough/torn edge effect

### Phase 7 — Workplane Extras
- [ ] Grid + ruler overlay
- [ ] Snap to grid
- [ ] Page background colour picker

### Phase 8 — Project Save/Load
- [ ] `.snipzaic` ZIP format
- [ ] New / Open / Save / Save As dialogs

### Phase 9 — Export
- [ ] PNG export (choose DPI)
- [ ] PDF export

### Phase 10 — Polish & Distribution
- [ ] Undo/redo (all operations)
- [ ] Keyboard shortcuts
- [ ] Windows `.exe` build + test
- [ ] AppImage for Linux

---

## Open Questions / Decisions Needed

1. **Snip Tray position** — below the browser, or a separate collapsible panel? 
2. **Export DPI** — default 300 DPI for print, or let user choose?
3. **Undo/redo scope** — all operations including effects, or just placement/transforms?
4. **Torn edge effect** — real-time on canvas, or applied on export only (performance question)?
5. **App name confirmed as SnipZaic?**
