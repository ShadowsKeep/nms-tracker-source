"""
NMS Tracker — Desktop Entry Point
Shadowskeep LLC
"""
import sys
import os
from pathlib import Path

# Add project root to sys.path so 'app' package is importable
project_root = str(Path(__file__).parent.parent) if not getattr(sys, 'frozen', False) else sys._MEIPASS  # type: ignore
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# ── Qt WebEngine must be configured before QApplication ────────
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-logging')

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from qt_host.window import TrackerWindow, APP_NAME, COMPANY, VERSION
from qt_host.server_thread import FlaskThread
from app import create_app


def main():
    # High DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName(APP_NAME)
    qt_app.setOrganizationName(COMPANY)
    qt_app.setApplicationVersion(VERSION)
    # The window hides to the tray on close; only the tray "Quit" ends the app.
    qt_app.setQuitOnLastWindowClosed(False)

    # Show the window (with animated splash) immediately …
    window = TrackerWindow()
    window.show()

    # … while Flask (DB seed, enrichment, bind) starts in the background.
    server = FlaskThread(create_app, host='127.0.0.1', ports=(5183, 0))
    server.server_ready.connect(window.load_url)
    server.server_error.connect(window.show_error)
    server.start()

    # Graceful shutdown of the WSGI server
    qt_app.aboutToQuit.connect(server.stop)

    sys.exit(qt_app.exec())


if __name__ == '__main__':
    main()
