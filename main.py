import sys
from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow
from ui.new_project_dialog import NewProjectDialog


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SnipZaic")
    app.setOrganizationName("SnipZaic")

    dialog = NewProjectDialog()
    if dialog.exec() != NewProjectDialog.DialogCode.Accepted:
        sys.exit(0)

    project = dialog.get_project()
    window = MainWindow(project)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
