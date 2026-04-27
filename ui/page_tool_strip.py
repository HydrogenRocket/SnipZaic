from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QButtonGroup
from PyQt6.QtCore import pyqtSignal, Qt


class _ToolBtn(QPushButton):
    def __init__(self, label: str, tooltip: str):
        super().__init__(label)
        self.setFixedSize(36, 36)
        self.setToolTip(tooltip)
        self.setCheckable(True)


class PageToolStrip(QWidget):
    """Vertical strip of workplane tools (right edge of the window)."""

    tool_changed = pyqtSignal(str)

    _TOOLS = [
        ("A", "auto",   "Auto — smart cursor: move or trim depending on context"),
        ("M", "move",   "Move Snip — drag to reposition"),
        ("T", "trim",   "Trim Snip — snap to edge, drag to opposite edge, removes smaller piece"),
        ("L", "layers", "Layer order — drag snip up/down the stack  [Phase 4]"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(44)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: list[QPushButton] = []

        for label, tool_id, tip in self._TOOLS:
            btn = _ToolBtn(label, tip)
            if tool_id in ("layers",):
                btn.setEnabled(False)
            self._group.addButton(btn)
            self._buttons.append(btn)
            layout.addWidget(btn)

        # Auto selected by default
        self._buttons[0].setChecked(True)
        self._current = "auto"

        layout.addStretch()
        self._group.buttonToggled.connect(self._on_toggled)

    def _on_toggled(self, btn: QPushButton, checked: bool):
        if checked:
            idx = self._buttons.index(btn)
            self._current = self._TOOLS[idx][1]
            self.tool_changed.emit(self._current)

    @property
    def current_tool(self) -> str:
        return self._current
