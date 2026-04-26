from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QComboBox,
    QDialogButtonBox, QLabel
)
from PyQt6.QtCore import Qt
from core.project import Project, PAGE_SIZES


class NewProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Project — SnipZaic")
        self.setMinimumWidth(300)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        layout = QVBoxLayout(self)

        title = QLabel("Create a new collage project")
        title.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 8px;")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)

        self.size_combo = QComboBox()
        self.size_combo.addItems(list(PAGE_SIZES.keys()))
        self.size_combo.setCurrentText("A4")
        form.addRow("Page size:", self.size_combo)

        self.orientation_combo = QComboBox()
        self.orientation_combo.addItems(["Portrait", "Landscape"])
        form.addRow("Orientation:", self.orientation_combo)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_project(self) -> Project:
        size = self.size_combo.currentText()
        landscape = self.orientation_combo.currentText() == "Landscape"
        return Project.new(size, landscape)
