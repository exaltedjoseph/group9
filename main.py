"""Study Library: launch the desktop app."""
from __future__ import annotations

import sys
import traceback


def _set_app_user_model_id() -> None:
    """Give the process its own taskbar identity so Windows shows our icon, not Python's."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("StudyLibrary.Desktop")
        except Exception:
            pass


def main() -> int:
    _set_app_user_model_id()
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setApplicationName("Study Library")
    QApplication.setOrganizationName("StudyLibrary")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    from app.core.gitops import GitManager
    from app.core.library import Library, LibraryError
    from app.core.settings import Settings
    from app.icons import app_icon
    from app.theme import font, load_bundled_fonts, theme
    from app.ui.controls import install_popup_styling
    from app.ui.window import MainWindow

    load_bundled_fonts()
    install_popup_styling(app)
    app.setFont(font("body"))
    app.setWindowIcon(app_icon())

    settings = Settings()
    theme().set_mode(settings.appearance())

    try:
        library = Library(settings.library_path())
    except (LibraryError, OSError) as exc:
        from app.ui.alert import confirm
        confirm(None, "The library couldn\u2019t be opened.", str(exc), "Quit", cancel_text="", destructive=False)
        return 1

    git = GitManager(library.root, enabled=settings.git_enabled(), auto_push=settings.auto_push(),
                     user_name=settings.user_name())
    if settings.git_enabled() and git.available():
        try:
            git.ensure_repo()
        except Exception:
            traceback.print_exc()

    window = MainWindow(settings, library, git)
    window.show()
    code = app.exec()

    git.shutdown()
    library.close()
    settings.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
