from dataclasses import dataclass, field
from PyQt6.QtGui import QPixmap


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
