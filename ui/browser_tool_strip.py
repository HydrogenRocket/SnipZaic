from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QButtonGroup
from PyQt6.QtCore import pyqtSignal, Qt


class _ToolBtn(QPushButton):
    def __init__(self, label: str, tooltip: str):
        super().__init__(label)
        self.setFixedSize(36, 36)
        self.setToolTip(tooltip)
        self.setCheckable(True)


class BrowserToolStrip(QWidget):
    """Vertical strip of browser-side snip tools (sits between the two panels)."""

    tool_changed = pyqtSignal(str)  # tool id, or "" when deactivated

    _TOOLS = [
        ("R", "rect_snip", "Rectangle Snip — drag to cut a rectangle"),
        ("P", "poly_snip", "Polygon Snip — click points, Enter or double-click to close"),
        ("F", "free_snip", "Freehand Snip — drag freely to cut"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(44)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Non-exclusive so the active button can be clicked again to deactivate
        self._group = QButtonGroup(self)
        self._group.setExclusive(False)
        self._buttons: list[QPushButton] = []

        for label, tool_id, tip in self._TOOLS:
            btn = _ToolBtn(label, tip)
            self._group.addButton(btn)
            self._buttons.append(btn)
            layout.addWidget(btn)
            btn.clicked.connect(lambda checked, b=btn: self._on_clicked(b, checked))

        layout.addStretch()

    def _on_clicked(self, clicked_btn: QPushButton, checked: bool):
        if checked:
            # Uncheck every other button manually (since group is non-exclusive)
            for btn in self._buttons:
                if btn is not clicked_btn:
                    btn.setChecked(False)
            idx = self._buttons.index(clicked_btn)
            self.tool_changed.emit(self._TOOLS[idx][1])
        else:
            self.tool_changed.emit("")

    def deactivate(self):
        """Uncheck all buttons without emitting tool_changed."""
        for btn in self._buttons:
            btn.setChecked(False)
