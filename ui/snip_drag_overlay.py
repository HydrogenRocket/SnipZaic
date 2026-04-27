from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer, pyqtSignal
from PyQt6.QtGui import QPainter, QPixmap, QColor, QTransform


class SnipDragOverlay(QWidget):
    """
    Transparent full-panel overlay shown while a just-cut snip is being dragged
    from the browser to the workplane.

    The snip sits at the cut location until the user clicks and holds — then it
    follows the cursor while held, drops on release.
    Right-click or Escape cancels.

    Parent must be the main window's central widget so the overlay spans both panels.
    """

    # pixmap, outline_path (QPainterPath|None), drop pos in this widget's coords
    dropped = pyqtSignal(QPixmap, object, QPointF)
    cancelled = pyqtSignal()

    _STEPS = 8
    _INTERVAL_MS = 18       # 8 × 18 ms ≈ 144 ms total rise animation
    _SCALE_START = 0.82
    _HOVER_SCALE = 1.02     # subtle enlarge when cursor is over the snip

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hide()

        self._pixmap: QPixmap | None = None
        self._outline = None
        self._pos = QPointF(0, 0)
        self._drag_anchor = QPointF(0, 0)
        self._drag_snip_origin = QPointF(0, 0)
        self._dragging = False
        self._hovering = False
        self._scale = 1.0
        self._step = 0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------ #
    # Public
    # ------------------------------------------------------------------ #

    def start_drag(self, pixmap: QPixmap, outline_path, cut_center: QPointF):
        """Show snip at cut_center with rise animation. User must click-drag to move it."""
        self._pixmap = pixmap
        self._outline = outline_path
        self._pos = cut_center
        self._dragging = False
        self._hovering = False
        self._scale = self._SCALE_START
        self._step = 0

        self._show_at(cut_center)
        self._timer.start(self._INTERVAL_MS)
        self.update()

    def resume(self, pixmap: QPixmap, outline_path, pos: QPointF):
        """Re-show at pos with no animation (used when a drop is rejected)."""
        self._pixmap = pixmap
        self._outline = outline_path
        self._pos = pos
        self._dragging = False
        self._hovering = False
        self._scale = 1.0
        self._step = self._STEPS

        self._show_at(pos)
        self.update()

    def _show_at(self, pos: QPointF):
        self.move(0, 0)
        self.resize(self.parent().size())
        self.raise_()
        self.show()
        self.setFocus()

    # ------------------------------------------------------------------ #
    # Animation
    # ------------------------------------------------------------------ #

    def _tick(self):
        self._step += 1
        t = self._step / self._STEPS
        self._scale = self._SCALE_START + (1.0 - self._SCALE_START) * t
        self.update()
        if self._step >= self._STEPS:
            self._timer.stop()
            self._scale = 1.0

    # ------------------------------------------------------------------ #
    # Painting
    # ------------------------------------------------------------------ #

    def paintEvent(self, event):
        if self._pixmap is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w = self._pixmap.width() * self._scale
        h = self._pixmap.height() * self._scale
        x = self._pos.x() - w / 2
        y = self._pos.y() - h / 2
        rect = QRectF(x, y, w, h)

        # Layered soft drop-shadow — shape-aware for poly/freehand snips
        painter.setPen(Qt.PenStyle.NoPen)
        if self._outline is not None:
            t = QTransform()
            t.translate(x, y)
            t.scale(w, h)
            shadow_shape = t.map(self._outline)
            for offset, alpha in ((10, 30), (7, 28), (4, 22), (2, 15)):
                painter.setBrush(QColor(0, 0, 0, alpha))
                painter.drawPath(shadow_shape.translated(offset, offset))
        else:
            for offset, alpha in ((10, 30), (7, 28), (4, 22), (2, 15)):
                painter.fillRect(rect.translated(offset, offset), QColor(0, 0, 0, alpha))

        painter.drawPixmap(rect, self._pixmap, QRectF(self._pixmap.rect()))
        painter.end()

    # ------------------------------------------------------------------ #
    # Input
    # ------------------------------------------------------------------ #

    def _snip_rect(self) -> QRectF:
        if self._pixmap is None:
            return QRectF()
        w = self._pixmap.width()
        h = self._pixmap.height()
        return QRectF(self._pos.x() - w / 2, self._pos.y() - h / 2, w, h)

    def mouseMoveEvent(self, event):
        if self._dragging:
            delta = event.position() - self._drag_anchor
            self._pos = self._drag_snip_origin + delta
            self.update()
        elif self._step >= self._STEPS:
            # Hover scale: only when animation is done and not dragging
            over = self._snip_rect().contains(event.position())
            if over != self._hovering:
                self._hovering = over
                self._scale = self._HOVER_SCALE if over else 1.0
                self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._hovering = False
            self._scale = 1.0
            self._drag_anchor = event.position()
            self._drag_snip_origin = QPointF(self._pos)
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            self._finish(drop=False)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._finish(drop=True)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._finish(drop=False)

    def _finish(self, drop: bool):
        self._timer.stop()
        pos = QPointF(self._pos)
        pixmap = self._pixmap
        outline = self._outline
        self._pixmap = None
        self._dragging = False
        self._hovering = False
        self.hide()
        if drop and pixmap is not None:
            self.dropped.emit(pixmap, outline, pos)
        else:
            self.cancelled.emit()
