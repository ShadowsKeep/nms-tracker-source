"""
Main application window — PyQt6 + QWebEngineView.
Shadowskeep LLC — NMS Tracker (No Man's Sky companion)

Startup sequence:
  1. A plain Qt "boot" widget (brown, no font dependency) covers the
     Chromium cold start.
  2. The web view loads the local animated splash (app/static/splash.html)
     and is shown once it has painted.
  3. When Flask signals ready AND the splash has been visible for at least
     MIN_SPLASH_MS, the splash fades out and the view navigates to Flask.
"""
import os
import sys
from pathlib import Path

from PyQt6.QtCore import QUrl, Qt, QTimer, QElapsedTimer
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QDesktopServices
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QLabel, QApplication,
    QSystemTrayIcon, QMenu, QStackedWidget,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEngineSettings, QWebEnginePage, QWebEngineProfile,
)


APP_NAME = 'NMS Tracker'
COMPANY  = 'Shadowskeep LLC'
VERSION  = '1.2.0'

# Everything in the web UI is rendered 25% larger than authored.
UI_ZOOM = 1.25

MIN_SPLASH_MS = 2400   # keep the splash visible at least this long once it has painted
FADE_MS       = 350    # must match the fade duration in splash.html

BG_COLOR = '#080b14'   # --bg, matches the web UI shell

LOCAL_HOSTS = {'127.0.0.1', 'localhost'}


def _resource_path(*parts: str) -> Path:
    """Absolute path to a bundled resource (works frozen and in dev)."""
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent.parent
    return base.joinpath(*parts)


def _make_fallback_icon() -> QIcon:
    """Generate a simple green pixel icon if no .ico file is present."""
    pix = QPixmap(32, 32)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.fillRect(0, 0, 32, 32, QColor('#0d1220'))
    painter.fillRect(6, 6, 20, 20, QColor('#ff4f3a'))
    painter.fillRect(11, 11, 10, 10, QColor('#0d1220'))
    painter.end()
    return QIcon(pix)


class AppPage(QWebEnginePage):
    """Page that keeps the app view on Flask and sends external links to the OS browser."""

    def __init__(self, profile: QWebEngineProfile, parent=None):
        super().__init__(profile, parent)
        self.newWindowRequested.connect(self._on_new_window)

    @staticmethod
    def _is_external(url: QUrl) -> bool:
        return url.scheme() in ('http', 'https') and url.host() not in LOCAL_HOSTS

    def _on_new_window(self, request):
        # target="_blank" anchors and window.open() both land here.
        url = request.requestedUrl()
        if url.scheme() in ('http', 'https'):
            QDesktopServices.openUrl(url)

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:
        if is_main_frame and self._is_external(url):
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


class BootScreen(QWidget):
    """Plain brown widget shown before Chromium paints, and on fatal errors."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f'background: {BG_COLOR};')
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label = QLabel('')
        self.label.setStyleSheet(
            'font-family: Consolas, monospace; font-size: 16px; '
            'color: #ff7a5c; padding: 24px;'
        )
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        self.sub = QLabel(f'{COMPANY} — v{VERSION}')
        self.sub.setStyleSheet('font-family: Consolas, monospace; font-size: 14px; color: #8b9bb8;')
        self.sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.sub)

    def show_error(self, msg: str):
        self.label.setText(f'❌  Could not start {APP_NAME}\n\n{msg}')


class TrackerWindow(QMainWindow):
    """Main PyQt6 window that hosts the Flask web app."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'{APP_NAME} — {COMPANY}')
        self.setStyleSheet(f'QMainWindow {{ background: {BG_COLOR}; }}')

        # Splash state
        self._clock = QElapsedTimer()
        self._clock.start()
        self._splash_ready = False
        self._pending_url = None
        self._phase = 'splash'        # 'splash' | 'app' | 'error'
        self._tray_tip_shown = False

        # Window icon
        ico_path = _resource_path('app', 'static', 'img', 'icon.ico')
        self.setWindowIcon(QIcon(str(ico_path)) if ico_path.exists() else _make_fallback_icon())

        # Sizing: the collect table wants ~1000 CSS px; at UI_ZOOM that is ~1250.
        # Clamp to the available screen so small laptops still open.
        screen = QApplication.primaryScreen().availableGeometry()
        default_w = min(1600, screen.width() - 40)
        default_h = min(1000, screen.height() - 40)
        self.setMinimumSize(min(1150, default_w), min(760, default_h))
        self.resize(default_w, default_h)
        self.move(screen.center() - self.rect().center())

        # Stack: boot screen (0) / web view (1)
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)
        self._boot = BootScreen()
        self._stack.addWidget(self._boot)

        self._web = QWebEngineView()
        self._web.setPage(AppPage(self._make_profile(), self._web))
        page = self._web.page()
        page.setBackgroundColor(QColor(BG_COLOR))
        settings = page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        self._web.setZoomFactor(UI_ZOOM)
        self._web.loadFinished.connect(self._on_load_finished)
        self._stack.addWidget(self._web)

        self._stack.setCurrentWidget(self._boot)
        self._web.setUrl(QUrl.fromLocalFile(str(_resource_path('app', 'static', 'splash.html'))))

        # System tray
        self._setup_tray()

    # ── WebEngine profile (persistent cache so wiki sprites survive offline) ──
    def _make_profile(self) -> QWebEngineProfile:
        profile = QWebEngineProfile('nms-tracker', self)
        try:
            from app import get_data_dir
            store = Path(get_data_dir()) / 'webengine'
            store.mkdir(parents=True, exist_ok=True)
            profile.setPersistentStoragePath(str(store))
            profile.setCachePath(str(store / 'cache'))
            profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        except Exception:  # noqa: BLE001 — fall back to memory cache
            pass
        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
        )
        return profile

    # ── Tray ─────────────────────────────────────────────────────────
    def _setup_tray(self):
        self._tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self.windowIcon(), self)
        menu = QMenu()
        menu.addAction('Show', self._restore)
        menu.addAction('Quit', QApplication.instance().quit)
        self._tray.setContextMenu(menu)
        self._tray.setToolTip(f'{APP_NAME} — {COMPANY}')
        self._tray.activated.connect(self._tray_clicked)
        self._tray.show()

    def _restore(self):
        self.showNormal()
        self.activateWindow()

    def _tray_clicked(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.DoubleClick,
                      QSystemTrayIcon.ActivationReason.Trigger):
            self._restore()

    # ── Splash → app transition ─────────────────────────────────────
    def _on_load_finished(self, ok: bool):
        # Keep zoom pinned across navigations (cheap, idempotent).
        self._web.setZoomFactor(UI_ZOOM)
        if self._phase != 'splash':
            return
        self._splash_ready = True
        self._stack.setCurrentWidget(self._web)
        self._clock.restart()          # count visibility from the first splash paint
        self._maybe_transition()

    def load_url(self, url: str):
        """Slot for FlaskThread.server_ready."""
        self._pending_url = url
        self._maybe_transition()

    def _maybe_transition(self):
        if self._phase != 'splash' or not (self._splash_ready and self._pending_url):
            return
        self._phase = 'fading'
        remaining = max(0, MIN_SPLASH_MS - self._clock.elapsed())
        QTimer.singleShot(remaining, self._fade_then_load)

    def _fade_then_load(self):
        self._web.page().runJavaScript('window.fadeOut && window.fadeOut();')
        QTimer.singleShot(FADE_MS, self._load_app)

    def _load_app(self):
        self._phase = 'app'
        self._web.setUrl(QUrl(self._pending_url))

    def show_error(self, msg: str):
        """Slot for FlaskThread.server_error — terminal state."""
        self._phase = 'error'
        self._boot.show_error(msg)
        self._stack.setCurrentWidget(self._boot)

    # ── Close → tray ─────────────────────────────────────────────────
    def closeEvent(self, event):
        """Minimize to tray instead of closing (if a tray exists)."""
        if self._tray is None:
            event.accept()
            QApplication.instance().quit()
            return
        event.ignore()
        self.hide()
        if not self._tray_tip_shown:
            self._tray_tip_shown = True
            self._tray.showMessage(
                APP_NAME,
                'Still running in the system tray. Double-click the icon to reopen, right-click to quit.',
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )
