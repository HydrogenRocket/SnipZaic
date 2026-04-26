from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRect, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QPixmap, QPainterPath, QBrush


class SnipOverlay(QWidget):
    region_selected = pyqtSignal(QRect)
    path_selected = pyqtSignal(QPainterPath)
    cancelled = pyqtSignal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._snapshot: QPixmap | None = None
        self._tool: str = "rect_snip"

        self._origin: QPointF | None = None
        self._current: QPointF | None = None

        self._poly_points: list[QPointF] = []

        self._free_path: QPainterPath | None = None
        self._free_drawing: bool = False

        self.setMouseTracking(True)
        self.hide()

    # --- public ---

    def activate(self, snapshot: QPixmap, tool: str = "rect_snip"):
        self._snapshot = snapshot
        self._tool = tool
        self._reset_state()
        self.raise_()
        self.show()
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocus()
        self.update()

    def reset(self):
        self._reset_state()
        self.update()

    def _reset_state(self):
        self._origin = None
        self._current = None
        self._poly_points = []
        self._free_path = None
        self._free_drawing = False

    # --- painting ---

    def paintEvent(self, event):
        if not self._snapshot:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawPixmap(
            QRectF(self.rect()),
            self._snapshot,
            QRectF(self._snapshot.rect()),
        )
        if self._tool == "rect_snip":
            self._paint_rect(painter)
        elif self._tool == "poly_snip":
            self._paint_poly(painter)
        elif self._tool == "free_snip":
            self._paint_free(painter)
        painter.end()

    def _paint_rect(self, painter: QPainter):
        if self._origin is None or self._current is None:
            return
        sel = QRectF(self._origin, self._current).normalized()
        painter.setPen(QPen(QColor(80, 160, 255), 2, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(sel)

    def _paint_poly(self, painter: QPainter):
        if not self._poly_points:
            return
        blue = QColor(80, 160, 255)
        painter.setPen(QPen(blue, 2))
        painter.setBrush(QBrush(QColor(80, 160, 255, 40)))

        path = QPainterPath()
        path.moveTo(self._poly_points[0])
        for pt in self._poly_points[1:]:
            path.lineTo(pt)
        if self._current is not None:
            path.lineTo(self._current)
        painter.drawPath(path)

        painter.setBrush(QBrush(Qt.GlobalColor.white))
        painter.setPen(QPen(blue, 1.5))
        for pt in self._poly_points:
            painter.drawEllipse(pt, 4.0, 4.0)

        # First point turns yellow when snap-close is possible
        if len(self._poly_points) > 2:
            painter.setBrush(QBrush(QColor(255, 220, 60)))
            painter.drawEllipse(self._poly_points[0], 6.0, 6.0)

    def _paint_free(self, painter: QPainter):
        if self._free_path is None or self._free_path.isEmpty():
            return
        painter.setPen(QPen(QColor(80, 160, 255), 2))
        painter.setBrush(QBrush(QColor(80, 160, 255, 40)))
        painter.drawPath(self._free_path)

    # --- mouse ---

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pt: QPointF = event.position()

        if self._tool == "rect_snip":
            self._origin = pt
            self._current = pt

        elif self._tool == "poly_snip":
            if len(self._poly_points) > 2:
                d = pt - self._poly_points[0]
                if abs(d.x()) + abs(d.y()) < 15:
                    self._finish_polygon()
                    return
            self._poly_points.append(pt)
            self._current = pt
            self.update()

        elif self._tool == "free_snip":
            self._free_path = QPainterPath()
            self._free_path.moveTo(pt)
            self._free_drawing = True

    def mouseMoveEvent(self, event):
        self._current = event.position()
        if self._tool == "rect_snip" and self._origin is not None:
            self.update()
        elif self._tool == "poly_snip" and self._poly_points:
            self.update()
        elif self._tool == "free_snip" and self._free_drawing and self._free_path:
            self._free_path.lineTo(self._current)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._tool == "rect_snip" and self._origin is not None:
            sel = QRectF(self._origin, event.position()).normalized().toRect()
            self._origin = None
            self._current = None
            if sel.width() > 5 and sel.height() > 5:
                self.region_selected.emit(sel)
            else:
                self.cancelled.emit()

        elif self._tool == "free_snip" and self._free_drawing:
            self._free_drawing = False
            if self._free_path and not self._free_path.isEmpty():
                self._free_path.closeSubpath()
                br = self._free_path.boundingRect()
                if br.width() > 5 and br.height() > 5:
                    self.path_selected.emit(self._free_path)
                    return
            self.cancelled.emit()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._tool == "poly_snip":
            # Remove the point added by the first press of this double-click
            if self._poly_points:
                self._poly_points.pop()
            self._finish_polygon()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._reset_state()
            self.cancelled.emit()
            self.hide()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._tool == "poly_snip":
                self._finish_polygon()

    def _finish_polygon(self):
        if len(self._poly_points) < 3:
            self.cancelled.emit()
            return
        path = QPainterPath()
        path.moveTo(self._poly_points[0])
        for pt in self._poly_points[1:]:
            path.lineTo(pt)
        path.closeSubpath()
        self.path_selected.emit(path)
