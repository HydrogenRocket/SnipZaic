from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QPixmap, QCursor,
    QPainterPath, QTransform, QBrush,
)

from core.project import Project
from core.snip import Snip

MM_TO_INCH = 1 / 25.4
SCREEN_DPI = 96
_SNAP_DIST = 12  # px


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _closest_on_segment(p: QPointF, a: QPointF, b: QPointF) -> tuple[QPointF, float]:
    ab = QPointF(b.x() - a.x(), b.y() - a.y())
    len_sq = ab.x() ** 2 + ab.y() ** 2
    if len_sq < 1e-9:
        return a, 0.0
    t = ((p.x() - a.x()) * ab.x() + (p.y() - a.y()) * ab.y()) / len_sq
    t = max(0.0, min(1.0, t))
    return QPointF(a.x() + t * ab.x(), a.y() + t * ab.y()), t


def _polygon_area(pts: list[QPointF]) -> float:
    n = len(pts)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += pts[i].x() * pts[j].y()
        area -= pts[j].x() * pts[i].y()
    return abs(area) * 0.5


def _path_vertices(path: QPainterPath) -> list[QPointF]:
    """
    Convert a QPainterPath to a flat list of polygon vertices.
    Uses toSubpathPolygons so bezier curves (from intersected()) are
    approximated to straight segments automatically.
    Takes the longest subpath if the path has multiple.
    """
    polys = path.toSubpathPolygons()
    if not polys:
        return []
    poly = max(polys, key=len)
    pts = [QPointF(p.x(), p.y()) for p in poly]
    # Remove explicit closing duplicate added by Qt
    if len(pts) > 1:
        f, l = pts[0], pts[-1]
        if abs(f.x() - l.x()) < 0.5 and abs(f.y() - l.y()) < 0.5:
            pts.pop()
    return pts


def _split_polygon(
    pts: list[QPointF],
    pt_a: QPointF, seg_a: int,
    pt_b: QPointF, seg_b: int,
) -> tuple[list[QPointF], list[QPointF]] | None:
    """
    Split polygon 'pts' (implicit close from last→first) with a chord from
    pt_a (on segment seg_a) to pt_b (on segment seg_b).
    Returns (poly1, poly2) or None if degenerate (same segment).
    """
    n = len(pts)
    if n < 3 or seg_a == seg_b:
        return None

    poly1 = [pt_a]
    i = (seg_a + 1) % n
    for _ in range(n + 1):
        poly1.append(pts[i])
        if i == seg_b:
            break
        i = (i + 1) % n
    poly1.append(pt_b)

    poly2 = [pt_b]
    i = (seg_b + 1) % n
    for _ in range(n + 1):
        poly2.append(pts[i])
        if i == seg_a:
            break
        i = (i + 1) % n
    poly2.append(pt_a)

    return poly1, poly2


# ---------------------------------------------------------------------------

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

        # Trim tool state
        self._trim_hover: tuple[Snip, QPointF, int, list] | None = None
        self._trim_snip: Snip | None = None
        self._trim_start: QPointF | None = None
        self._trim_start_seg: int = -1
        self._trim_end: QPointF | None = None
        self._trim_end_seg: int = -1
        self._trim_verts: list[QPointF] = []   # outline verts in screen coords
        self._trim_mouse: QPointF | None = None

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

    # --- outline helpers ---

    def _effective_outline(self, snip: Snip) -> QPainterPath:
        """Visible shape as a normalized (0..1) QPainterPath."""
        if snip.outline_path is not None:
            base = snip.outline_path
        else:
            base = QPainterPath()
            base.addRect(QRectF(0, 0, 1, 1))
        return base if snip.clip_path is None else base.intersected(snip.clip_path)

    def _effective_outline_screen(self, snip: Snip) -> QPainterPath:
        """Visible shape in widget (screen) coordinates."""
        sr = self._snip_rect(snip)
        t = QTransform()
        t.translate(sr.x(), sr.y())
        t.scale(sr.width(), sr.height())
        return t.map(self._effective_outline(snip))

    # --- trim helpers ---

    def _snap_to_snip_edge(
        self, pos: QPointF, restrict_to: Snip | None = None
    ) -> tuple[Snip, QPointF, int, list[QPointF]] | None:
        """
        Find the nearest point on any snip's visible outline within _SNAP_DIST px.
        Returns (snip, snapped_point, segment_index, outline_vertices) or None.
        Segment i runs from verts[i] to verts[(i+1) % len(verts)].
        """
        candidates = (
            [restrict_to] if restrict_to is not None
            else list(reversed(self.project.snips))
        )
        for snip in candidates:
            if snip is None or snip.locked:
                continue
            screen_path = self._effective_outline_screen(snip)
            verts = _path_vertices(screen_path)
            if len(verts) < 2:
                continue
            n = len(verts)
            best_d2 = _SNAP_DIST ** 2
            best_pt: QPointF | None = None
            best_seg = -1
            for i in range(n):
                pt, _ = _closest_on_segment(pos, verts[i], verts[(i + 1) % n])
                dx = pos.x() - pt.x()
                dy = pos.y() - pt.y()
                d2 = dx * dx + dy * dy
                if d2 < best_d2:
                    best_d2 = d2
                    best_pt = pt
                    best_seg = i
            if best_pt is not None:
                return snip, best_pt, best_seg, verts
        return None

    def _apply_trim(
        self,
        snip: Snip,
        pt_a: QPointF, seg_a: int,
        pt_b: QPointF, seg_b: int,
        verts: list[QPointF],
    ):
        result = _split_polygon(verts, pt_a, seg_a, pt_b, seg_b)
        if result is None:
            return
        poly1, poly2 = result
        keep = poly1 if _polygon_area(poly1) >= _polygon_area(poly2) else poly2

        sr = self._snip_rect(snip)
        w, h = sr.width(), sr.height()
        ox, oy = sr.x(), sr.y()
        norm = [QPointF((p.x() - ox) / w, (p.y() - oy) / h) for p in keep]

        new_path = QPainterPath()
        new_path.moveTo(norm[0])
        for pt in norm[1:]:
            new_path.lineTo(pt)
        new_path.closeSubpath()

        snip.clip_path = (
            new_path if snip.clip_path is None
            else snip.clip_path.intersected(new_path)
        )
        self.update()

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

    def add_snip(self, pixmap: QPixmap, outline_path=None):
        mm_per_px = 25.4 / SCREEN_DPI
        snip_w_mm = pixmap.width() * mm_per_px
        snip_h_mm = pixmap.height() * mm_per_px
        x_mm = max(0.0, (self.project.page_width_mm - snip_w_mm) / 2)
        y_mm = max(0.0, (self.project.page_height_mm - snip_h_mm) / 2)
        snip = Snip(pixmap=pixmap, x_mm=x_mm, y_mm=y_mm, outline_path=outline_path)
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
        painter.fillRect(pr.translated(5, 5), QColor(0, 0, 0, 70))
        painter.fillRect(pr, QColor(self.project.page_bg_colour))
        painter.setPen(QPen(QColor(180, 180, 180), 1))
        painter.drawRect(pr)

        painter.save()
        painter.setClipRect(pr)
        for snip in self.project.snips:
            self._draw_snip(painter, snip)
        painter.restore()

        if self.active_tool == "trim":
            self._draw_trim_overlay(painter)

        painter.end()

    def _draw_snip(self, painter: QPainter, snip: Snip):
        sr = self._snip_rect(snip)

        painter.save()
        painter.translate(sr.x(), sr.y())

        if snip.clip_path is not None:
            t = QTransform().scale(sr.width(), sr.height())
            painter.setClipPath(t.map(snip.clip_path), Qt.ClipOperation.IntersectClip)

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

        if snip is self._selected_snip:
            # Stroke the actual visible shape, not the bounding box
            if snip.outline_path is not None:
                base = snip.outline_path
            else:
                base = QPainterPath()
                base.addRect(QRectF(0, 0, 1, 1))
            effective = (
                base if snip.clip_path is None
                else base.intersected(snip.clip_path)
            )
            t = QTransform()
            t.translate(sr.x(), sr.y())
            t.scale(sr.width(), sr.height())
            painter.setPen(QPen(QColor(80, 160, 255), 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(t.map(effective))

    def _draw_trim_overlay(self, painter: QPainter):
        # Snap indicator when hovering (not mid-drag)
        if self._trim_hover and self._trim_snip is None:
            _, pt, _, _ = self._trim_hover
            painter.setPen(QPen(QColor(255, 220, 0), 2))
            painter.setBrush(QBrush(QColor(255, 220, 0, 200)))
            painter.drawEllipse(pt, 6.0, 6.0)

        if self._trim_snip is None or self._trim_start is None:
            return

        end_pt = self._trim_end if self._trim_end is not None else self._trim_mouse
        if end_pt is None:
            return

        painter.setPen(QPen(QColor(220, 60, 60), 2))
        painter.drawLine(self._trim_start, end_pt)

        if self._trim_end is not None:
            painter.setPen(QPen(QColor(255, 220, 0), 2))
            painter.setBrush(QBrush(QColor(255, 220, 0, 200)))
            painter.drawEllipse(self._trim_end, 6.0, 6.0)

        # Red shade on the piece that will be removed
        if (self._trim_end is not None
                and self._trim_end_seg != -1
                and self._trim_end_seg != self._trim_start_seg
                and self._trim_verts):
            result = _split_polygon(
                self._trim_verts,
                self._trim_start, self._trim_start_seg,
                self._trim_end, self._trim_end_seg,
            )
            if result:
                poly1, poly2 = result
                remove = poly2 if _polygon_area(poly1) >= _polygon_area(poly2) else poly1
                path = QPainterPath()
                path.moveTo(remove[0])
                for pt in remove[1:]:
                    path.lineTo(pt)
                path.closeSubpath()
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(220, 60, 60, 90)))
                painter.drawPath(path)

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
            if self.active_tool == "trim":
                snap = self._snap_to_snip_edge(event.position())
                if snap:
                    snip, pt, seg, verts = snap
                    self._trim_snip = snip
                    self._trim_start = pt
                    self._trim_start_seg = seg
                    self._trim_verts = verts
                    self._trim_end = None
                    self._trim_end_seg = -1
                    self._trim_hover = None
                return

            if self.active_tool in ("auto", "move"):
                snip = self._snip_at(event.position())
                if snip:
                    self._drag_snip = snip
                    self._selected_snip = snip
                    pos_mm = self._widget_to_page_mm(event.position())
                    self._drag_offset_mm = QPointF(
                        pos_mm.x() - snip.x_mm, pos_mm.y() - snip.y_mm
                    )
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

        if self.active_tool == "trim":
            self._trim_mouse = event.position()
            if self._trim_snip is not None and self._trim_start is not None:
                snap = self._snap_to_snip_edge(event.position(), restrict_to=self._trim_snip)
                if snap:
                    _, pt, seg, _ = snap
                    self._trim_end = pt
                    self._trim_end_seg = seg
                else:
                    self._trim_end = None
                    self._trim_end_seg = -1
                self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                self._trim_hover = self._snap_to_snip_edge(event.position())
                self.setCursor(
                    Qt.CursorShape.CrossCursor if self._trim_hover
                    else Qt.CursorShape.ArrowCursor
                )
            self.update()
            return

        if self._drag_snip and event.buttons() & Qt.MouseButton.LeftButton:
            pos_mm = self._widget_to_page_mm(event.position())
            self._drag_snip.x_mm = pos_mm.x() - self._drag_offset_mm.x()
            self._drag_snip.y_mm = pos_mm.y() - self._drag_offset_mm.y()
            self.update()
            return

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
            if self.active_tool == "trim":
                if (self._trim_snip is not None
                        and self._trim_start is not None
                        and self._trim_end is not None
                        and self._trim_start_seg != self._trim_end_seg
                        and self._trim_verts):
                    self._apply_trim(
                        self._trim_snip,
                        self._trim_start, self._trim_start_seg,
                        self._trim_end, self._trim_end_seg,
                        self._trim_verts,
                    )
                self._trim_snip = None
                self._trim_start = None
                self._trim_end = None
                self._trim_verts = []
                self._trim_hover = None
                self.update()
                return

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

    def add_snip(self, pixmap: QPixmap, outline_path=None):
        self.canvas.add_snip(pixmap, outline_path)

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
