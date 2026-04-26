from dataclasses import dataclass, field
from typing import List

PAGE_SIZES = {
    "A4":     (210, 297),
    "A3":     (297, 420),
    "A2":     (420, 594),
    "A1":     (594, 841),
    "Letter": (216, 279),
}


@dataclass
class Project:
    page_size_name: str = "A4"
    page_width_mm: float = 210
    page_height_mm: float = 297
    landscape: bool = False
    page_bg_colour: str = "#ffffff"
    snips: List = field(default_factory=list)

    @classmethod
    def new(cls, size_name: str = "A4", landscape: bool = False) -> "Project":
        w, h = PAGE_SIZES.get(size_name, PAGE_SIZES["A4"])
        if landscape:
            w, h = h, w
        return cls(
            page_size_name=size_name,
            page_width_mm=w,
            page_height_mm=h,
            landscape=landscape,
        )
