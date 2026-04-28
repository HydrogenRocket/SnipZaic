from dataclasses import dataclass, field
from PyQt6.QtGui import QPixmap, QPainterPath


@dataclass
class Snip:
    pixmap: QPixmap
    x_mm: float = 0.0
    y_mm: float = 0.0
    rotation: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    flipped_h: bool = False
    flipped_v: bool = False
    blend_mode: str = "normal"
    locked: bool = False
    stuck: bool = False         # permanently fixed to page; not selectable or editable
    # Normalized (0..1) trim clip — set by the trim tool, applied at render time.
    clip_path: QPainterPath | None = None
    # Normalized (0..1) original selection outline — set for poly/freehand snips.
    # None means the snip is a plain rectangle.
    outline_path: QPainterPath | None = None
