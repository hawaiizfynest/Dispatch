"""
Dispatch — security news triage and drafting desk.

Written by LJ "HawaiizFynest" Eblacas — Colorado Vista IT Solutions
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

# PyInstaller packs the modules into the executable itself, so none of the
# source-layout checking below applies to a build. Doing it anyway would look
# for a folder that a one-file exe has no reason to carry and quit before the
# window ever opens.
FROZEN = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")

if not FROZEN:
    # Run from anywhere: put this file's folder on the import path before the
    # package import below. Also covers launchers that skip the usual sys.path[0].
    HERE = Path(__file__).resolve().parent
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))

    if not (HERE / "dispatch" / "__init__.py").exists():
        sys.exit(
            "Dispatch cannot find its package folder.\n\n"
            f"Looked in: {HERE / 'dispatch'}\n\n"
            "main.py needs a 'dispatch' folder beside it, laid out like this:\n\n"
            "  dispatch\\\n"
            "      main.py\n"
            "      requirements.txt\n"
            "      dispatch\\\n"
            "          __init__.py\n"
            "          config.py, db.py, cluster.py, feeds.py, compose.py, defaults.py\n"
            "          ui\\\n"
            "              __init__.py\n"
            "              main_window.py, dialogs.py, theme.py, workers.py\n\n"
            "If every .py file is sitting loose in one folder, that is the problem.\n"
            "Extract the zip again and keep the folders it contains."
        )

from PyQt6.QtWidgets import QApplication, QMessageBox

from dispatch import __app_name__, __org__, __version__, config
from dispatch.db import Database
from dispatch.ui.main_window import MainWindow


def excepthook(exc_type, exc_value, exc_tb) -> None:
    """Show crashes instead of closing the window with no explanation."""
    text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    sys.__excepthook__(exc_type, exc_value, exc_tb)
    if QApplication.instance() is not None:
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(f"{__app_name__} hit an error")
        box.setText("Something broke. The details are below.")
        box.setDetailedText(text)
        box.exec()


def main() -> int:
    sys.excepthook = excepthook

    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(__org__)

    settings = config.load_settings()

    db = Database()
    db.seed_if_empty()

    window = MainWindow(db, settings)
    window.show()

    exit_code = app.exec()
    db.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
