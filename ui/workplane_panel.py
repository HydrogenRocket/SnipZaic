from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QPixmap, QCursor

from core.project import Project
from core.snip import Snip

MM_TO_INCH = 1 / 25.4
SCREEN_DPI = 96


class WorkplaneCanvas(QWidget):
    zoom_changed = pyqtSignal(float)

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.active_tool: str = "auto"

        self.zoom = 1.0
        self._pan_offset = QPointF(0, 0)
        self._pan_start = QPointF(0, 0)
        self._pan_origin = QPointF(0, 0)
        self._panning = False
        self._fit_pending = True

        self._selected_snip: Snip | None = None
        self._drag_snip: Snip | None = None
        self._drag_offset_mm = QPointF(0, 0)

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(300, 300)

    # --- coordinate helpers ---

    def _widget_per_mm(self) -> float:
        return SCREEN_DPI * MM_TO_INCH * self.zoom

    def page_rect(self) -> QRectF:
        wpm = self._widget_per_mm()
        pw = self.project.page_width_mm * wpm
        ph = self.project.page_height_mm * wpm
        x = (self.width() - pw) / 2 + self._pan_offset.x()
        y = (self.height() - ph) / 2 + self._pan_offset.y()
        return QRectF(x, y, pw, ph)

    def _widget_to_page_mm(self, pos: QPointF) -> QPointF:
        pr = self.page_rect()
        wpm = self._widget_per_mm()
        return QPointF((pos.x() - pr.x()) / wpm, (pos.y() - pr.y()) / wpm)

    def _snip_rect(self, snip: Snip) -> QRectF:
        pr = self.page_rect()
        wpm = self._widget_per_mm()
        sx = pr.x() + snip.x_mm * wpm
        sy = pr.y() + snip.y_mm * wpm
        sw = snip.pixmap.width() * self.zoom * snip.scale_x
        sh = snip.pixmap.height() * self.zoom * snip.scale_y
        return QRectF(sx, sy, sw, sh)

    def _snip_at(self, pos: QPointF) -> Snip | None:
        for snip in reversed(self.project.snips):
            if snip.locked:
                continue
            if self._snip_rect(snip).contains(pos):
                return snip
        return None

    # --- public API ---

    def fit_to_window(self):
        if self.width() < 10 or self.height() < 10:
            return
        pw = self.project.page_width_mm * SCREEN_DPI * MM_TO_INCH
        ph = self.project.page_height_mm * SCREEN_DPI * MM_TO_INCH
        margin = 48
        self.zoom = min(
            (self.width() - margin * 2) / pw,
            (self.height() - margin * 2) / ph,
            2.0,
        )
        self._pan_offset = QPointF(0, 0)
        self.update()
        self.zoom_changed.emit(self.zoom)

    def add_snip(self, pixmap: QPixmap):
        mm_per_px = 25.4 / SCREEN_DPI
        snip_w_mm = pixmap.width() * mm_per_px
        snip_h_mm = pixmap.height() * mm_per_px
        x_mm = max(0.0, (self.project.page_width_mm - snip_w_mm) / 2)
        y_mm = max(0.0, (self.project.page_height_mm - snip_h_mm) / 2)
        snip = Snip(pixmap=pixmap, x_mm=x_mm, y_mm=y_mm)
        self.project.snips.append(snip)
        self._selected_snip = snip
        self.update()

    # --- painting ---

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        painter.fillRect(self.rect(), QColor(64, 64, 64))

        pr = self.page_rect()

        # Drop shadow
        painter.fillRect(pr.translated(5, 5), QColor(0, 0, 0, 70))

        # Page background
        painter.fillRect(pr, QColor(self.project.page_bg_colour))
        painter.setPen(QPen(QColor(180, 180, 180), 1))
        painter.drawRect(pr)

        # Snips (clipped to page)
        painter.save()
        painter.setClipRect(pr)
        for snip in self.project.snips:
            self._draw_snip(painter, snip)
        painter.restore()

    def _draw_snip(self, painter: QPainter, snip: Snip):
        sr = self._snip_rect(snip)

        painter.save()
        painter.translate(sr.x(), sr.y())
        if snip.flipped_h:
            painter.scale(-1, 1)
            painter.translate(-sr.width(), 0)
        if snip.flipped_v:
            painter.scale(1, -1)
            painter.translate(0, -sr.height())
        if snip.rotation:
            cx, cy = sr.width() / 2, sr.height() / 2
            painter.translate(cx, cy)
            painter.rotate(snip.rotation)
            painter.translate(-cx, -cy)

        painter.drawPixmap(
            QRectF(0, 0, sr.width(), sr.height()),
            snip.pixmap,
            QRectF(snip.pixmap.rect()),
        )
        painter.restore()

        # Selection indicator
        if snip is self._selected_snip:
            painter.setPen(QPen(QColor(80, 160, 255), 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(sr.adjusted(-1, -1, 1, 1))

    # --- zoom / pan ---

    def _zoom_around(self, cursor: QPointF, factor: float):
        old = self.zoom
        self.zoom = max(0.05, min(8.0, self.zoom * factor))
        actual = self.zoom / old
        pr = self.page_rect()
        cx, cy = pr.x() + pr.width() / 2, pr.y() + pr.height() / 2
        self._pan_offset = QPointF(
            cursor.x() + (self._pan_offset.x() + cx - cursor.x()) * actual - cx,
            cursor.y() + (self._pan_offset.y() + cy - cursor.y()) * actual - cy,
        )
        self.update()
        self.zoom_changed.emit(self.zoom)

    # --- mouse events ---

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.position()
            self._pan_origin = QPointF(self._pan_offset)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            if self.active_tool in ("auto", "move"):
                snip = self._snip_at(event.position())
                if snip:
                    self._drag_snip = snip
                    self._selected_snip = snip
                    pos_mm = self._widget_to_page_mm(event.position())
                    self._drag_offset_mm = QPointF(
                        pos_mm.x() - snip.x_mm, pos_mm.y() - snip.y_mm
                    )
                    # Bring to top of stack
                    self.project.snips.remove(snip)
                    self.project.snips.append(snip)
                    self.update()
                else:
                    self._selected_snip = None
                    self.update()

    def mouseMoveEvent(self, event):
        if self._panning and event.buttons() & Qt.MouseButton.MiddleButton:
            self._pan_offset = self._pan_origin + (event.position() - self._pan_start)
            self.update()
            return

        if self._drag_snip and event.buttons() & Qt.MouseButton.LeftButton:
            pos_mm = self._widget_to_page_mm(event.position())
            self._drag_snip.x_mm = pos_mm.x() - self._drag_offset_mm.x()
            self._drag_snip.y_mm = pos_mm.y() - self._drag_offset_mm.y()
            self.update()
            return

        # Update cursor hint for auto tool
        if self.active_tool in ("auto", "move"):
            snip = self._snip_at(event.position())
            self.setCursor(
                Qt.CursorShape.SizeAllCursor if snip else Qt.CursorShape.ArrowCursor
            )

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_snip = None

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.12 if event.angleDelta().y() > 0 else 1 / 1.12
            self._zoom_around(event.position(), factor)
        else:
            super().wheelEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit_pending:
            self._fit_pending = False
            self.fit_to_window()

    def showEvent(self, event):
        super().showEvent(event)
        if self._fit_pending:
            self._fit_pending = False
            self.fit_to_window()


class WorkplanePanel(QWidget):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.canvas = WorkplaneCanvas(project)
        layout.addWidget(self.canvas)

    def set_project(self, project: Project):
        self.canvas.project = project
        self.canvas._fit_pending = True
        self.canvas.fit_to_window()

    def set_page_tool(self, tool: str):
        self.canvas.active_tool = tool

    def add_snip(self, pixmap: QPixmap):
        self.canvas.add_snip(pixmap)

    # Kept for menu action connections
    def _fit(self):
        self.canvas.fit_to_window()

    def _zoom_in(self):
        self.canvas._zoom_around(
            QPointF(self.canvas.width() / 2, self.canvas.height() / 2), 1.2
        )

    def _zoom_out(self):
        self.canvas._zoom_around(
            QPointF(self.canvas.width() / 2, self.canvas.height() / 2), 1 / 1.2
        )
