# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
python main.py
```

PyQt6-WebEngine is not always available via pip (version conflicts with system Qt). If the pip version fails, install via apt:

```bash
sudo apt install python3-pyqt6.qtwebengine
```

There are no tests and no build step — the app runs directly from source.

## Architecture

The window is a fixed split: `[BrowserPanel | BrowserToolStrip | WorkplanePanel | PageToolStrip]` in a `QHBoxLayout` with no `QSplitter`. Panels take `stretch=1`; strips are fixed-width.

### Snip flow (the core loop)

1. User activates a snip tool in `BrowserToolStrip` → `tool_changed` signal → `BrowserPanel.set_active_tool()`
2. `BrowserPanel._arm()` grabs the browser pixmap (`QWebEngineView.grab()`), hides the browser (size is retained via `setRetainSizeWhenHidden`), positions `SnipOverlay` over the exact browser geometry, and calls `overlay.activate(snapshot, tool)`
3. `SnipOverlay` draws the frozen snapshot as its background (no darkening). The user draws a selection. On completion the overlay emits `region_selected(QRect)` (rect snip) or `path_selected(QPainterPath)` (poly/free snip)
4. `BrowserPanel` crops the snapshot and — for shaped snips — creates a transparency-masked `QPixmap` via `QPainter.setClipPath()`. Emits `snip_ready(QPixmap)`
5. `MainWindow` forwards the pixmap to `WorkplanePanel.add_snip()` → `WorkplaneCanvas.add_snip()` → appends a `Snip` to `Project.snips` and triggers a repaint

**Why freeze-frame?** QWebEngineView renders via Vulkan on NVIDIA/Wayland. Native-window overlays are unreliable because the compositor Z-orders the Vulkan surface on top of everything. Hiding the browser and drawing a frozen pixmap is the only reliable approach.

### Coordinate systems

- Workplane positions are stored in **millimetres** in `Snip.x_mm / y_mm`
- `WorkplaneCanvas._widget_per_mm()` converts: `SCREEN_DPI (96) × MM_TO_INCH (1/25.4) × zoom`
- Snip pixel sizes → mm: `px × 25.4 / 96`
- Overlay selection coords are in logical overlay pixels; scaled to snapshot physical pixels using `snapshot.width() / overlay.width()` (DPR factor)

### Key files

| File | Role |
|---|---|
| `ui/snip_overlay.py` | Mode-aware overlay: rect, poly, freehand. All mouse coords use `QPointF` (required by `QPainterPath`). Always call `painter.end()` explicitly in `paintEvent`. |
| `ui/browser_panel.py` | Owns the snip lifecycle, stealth `QWebEngineProfile`, nav bar. `_arm()` must show the browser before `grab()` to handle tool switching. |
| `ui/workplane_panel.py` | `WorkplaneCanvas` — zoom/pan, snip rendering, move tool. `WorkplanePanel` is a thin wrapper that delegates to the canvas. |
| `core/snip.py` | `Snip` dataclass — pixmap + transform state. Transforms applied at render time (non-destructive). |
| `core/project.py` | `Project` dataclass — page dimensions (mm), bg colour, snip list. `Project.new(size_name, landscape)` is the factory. |

### Anti-bot setup

`browser_panel._make_profile()` creates a persistent `QWebEngineProfile` named `"SnipZaic"` with a Chrome 124 user agent, `en-GB` accept-language, persistent cookies, disk cache, and a `DocumentCreation / MainWorld` JS script that hides `navigator.webdriver`, fakes plugins, and adds `window.chrome`.

## Design constraints

- **No image import from disk.** All snips must come from the browser. This is intentional.
- Snip transforms (rotate, scale, flip) are applied at paint time — the original pixmap is never modified.
- The `QButtonGroup` for tool strips is `setExclusive(False)` so the active tool can be clicked again to deactivate. Exclusivity is enforced manually in `_on_clicked`.
- Nav buttons use `setFocusPolicy(NoFocus)` so keyboard input (Enter to search) stays in the browser.
