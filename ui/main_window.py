from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QMessageBox
from PyQt6.QtGui import QAction, QKeySequence, QPixmap, QCursor
from PyQt6.QtCore import Qt, QPointF

from core.project import Project
from core.snip import Snip
from ui.browser_panel import BrowserPanel
from ui.workplane_panel import WorkplanePanel
from ui.browser_tool_strip import BrowserToolStrip
from ui.page_tool_strip import PageToolStrip
from ui.new_project_dialog import NewProjectDialog
from ui.snip_drag_overlay import SnipDragOverlay

MM_TO_INCH = 1 / 25.4
SCREEN_DPI = 96


class MainWindow(QMainWindow):
    def __init__(self, project: Project):
        super().__init__()
        self.project = project

        self.setWindowTitle("SnipZaic")
        self.resize(1400, 900)

        # --- panels ---
        self.browser_panel = BrowserPanel()
        self.browser_tool_strip = BrowserToolStrip()
        self.workplane_panel = WorkplanePanel(project)
        self.page_tool_strip = PageToolStrip()

        # --- central layout: [browser | btool | workplane | ptool] ---
        central = QWidget()
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self.browser_panel, stretch=1)
        row.addWidget(self.browser_tool_strip)
        row.addWidget(self.workplane_panel, stretch=1)
        row.addWidget(self.page_tool_strip)
        self.setCentralWidget(central)

        # --- drag overlay (parented to central widget, spans everything) ---
        self._drag_overlay = SnipDragOverlay(central)
        self._drag_overlay.dropped.connect(self._on_drag_dropped)
        self._drag_overlay.cancelled.connect(self._on_drag_cancelled)

        # --- menu ---
        self._build_menu()

        # --- status bar ---
        self.statusBar()
        self.workplane_panel.canvas.zoom_changed.connect(self._update_status)
        self.workplane_panel.set_project(project)
        self._update_status(self.workplane_panel.canvas.zoom)

        # --- signals ---
        self.browser_tool_strip.tool_changed.connect(self.browser_panel.set_active_tool)
        self.page_tool_strip.tool_changed.connect(self.workplane_panel.set_page_tool)
        self.browser_panel.snip_ready.connect(self._on_snip_ready)

    # --- menu ---

    def _build_menu(self):
        menu = self.menuBar()

        file_menu = menu.addMenu("&File")

        new_act = QAction("&New Project…", self)
        new_act.setShortcut(QKeySequence.StandardKey.New)
        new_act.triggered.connect(self._new_project)
        file_menu.addAction(new_act)

        file_menu.addSeparator()

        quit_act = QAction("&Quit", self)
        quit_act.setShortcut(QKeySequence.StandardKey.Quit)
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        view_menu = menu.addMenu("&View")

        fit_act = QAction("Fit Page to Window", self)
        fit_act.setShortcut(QKeySequence("Ctrl+0"))
        fit_act.triggered.connect(self.workplane_panel._fit)
        view_menu.addAction(fit_act)

        zi_act = QAction("Zoom In", self)
        zi_act.setShortcut(QKeySequence.StandardKey.ZoomIn)
        zi_act.triggered.connect(self.workplane_panel._zoom_in)
        view_menu.addAction(zi_act)

        zo_act = QAction("Zoom Out", self)
        zo_act.setShortcut(QKeySequence.StandardKey.ZoomOut)
        zo_act.triggered.connect(self.workplane_panel._zoom_out)
        view_menu.addAction(zo_act)

        help_menu = menu.addMenu("&Help")
        about_act = QAction("&About SnipZaic", self)
        about_act.triggered.connect(self._show_about)
        help_menu.addAction(about_act)

    # --- snip drag flow ---

    def _on_snip_ready(self, pixmap: QPixmap, outline_path, cut_center: QPointF):
        # cut_center is already in central-widget coordinates (computed by BrowserPanel)
        self._drag_overlay.start_drag(pixmap, outline_path, cut_center)

    def _on_drag_dropped(self, pixmap: QPixmap, outline_path, pos: QPointF):
        """pos is in central-widget coordinates."""
        canvas = self.workplane_panel.canvas
        canvas_local = QPointF(canvas.mapFrom(self.centralWidget(), pos.toPoint()))

        on_canvas = (
            0 <= canvas_local.x() <= canvas.width()
            and 0 <= canvas_local.y() <= canvas.height()
        )
        if not on_canvas:
            # Dropped outside the workplane — put it back so the user can try again
            self._drag_overlay.resume(pixmap, outline_path, pos)
            return

        # Convert drop point to page-mm, centred on the cursor
        pos_mm = canvas._widget_to_page_mm(canvas_local)
        mm_per_px = 25.4 / SCREEN_DPI
        x_mm = pos_mm.x() - (pixmap.width() * mm_per_px) / 2
        y_mm = pos_mm.y() - (pixmap.height() * mm_per_px) / 2

        canvas.add_snip(pixmap, outline_path, x_mm=x_mm, y_mm=y_mm)
        self.browser_panel.rearm()

    def _on_drag_cancelled(self):
        # Snip is discarded; leave the browser showing for normal browsing
        pass

    # --- other slots ---

    def _new_project(self):
        dialog = NewProjectDialog(self)
        if dialog.exec() == NewProjectDialog.DialogCode.Accepted:
            self.project = dialog.get_project()
            self.workplane_panel.set_project(self.project)
            self._update_status(self.workplane_panel.canvas.zoom)

    def _update_status(self, zoom: float = 0):
        if not zoom:
            zoom = self.workplane_panel.canvas.zoom
        p = self.project
        self.statusBar().showMessage(
            f"{p.page_size_name} {'Landscape' if p.landscape else 'Portrait'}  "
            f"{int(p.page_width_mm)}×{int(p.page_height_mm)} mm  |  "
            f"Zoom: {int(zoom * 100)}%  |  "
            f"Ctrl+scroll to zoom · Middle-drag to pan"
        )

    def _show_about(self):
        QMessageBox.about(
            self,
            "About SnipZaic",
            "<b>SnipZaic</b><br>"
            "A browser-based collage and mosaic maker.<br><br>"
            "Browse the web on the left, snip pieces onto your page on the right.<br>"
            "All material comes from the browser — no file imports.",
        )
