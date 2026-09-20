"""
Flask server thread for PyQt6 integration.

Builds the Flask app and serves it with werkzeug's threaded WSGI server
inside a QThread. Emits `server_ready(url)` once the socket is bound and
`server_error(msg)` if anything goes wrong. `stop()` shuts the server down
cleanly (called from the GUI thread on quit).
"""
from typing import Callable, Optional, Sequence

from PyQt6.QtCore import QThread, pyqtSignal
from werkzeug.serving import ThreadedWSGIServer


class _ExclusiveServer(ThreadedWSGIServer):
    """WSGI server that refuses to share a port.

    werkzeug sets ``allow_reuse_address = True``; on Windows that lets a second
    instance bind an already-listening 127.0.0.1:5183 without error, after
    which connections are delivered to an arbitrary process. Disabling reuse
    makes the bind fail loudly so the port fallback below can kick in.
    """
    allow_reuse_address = False


class FlaskThread(QThread):
    """Runs the Flask app in a background thread."""
    server_ready = pyqtSignal(str)  # Emits the server URL when ready
    server_error = pyqtSignal(str)  # Emits error message

    def __init__(self, app_factory: Callable, host: str = '127.0.0.1',
                 ports: Sequence[int] = (5183, 0)):
        super().__init__()
        self._factory = app_factory
        self._host = host
        self._ports = tuple(ports)
        self._server: Optional[ThreadedWSGIServer] = None

    @property
    def url(self) -> Optional[str]:
        if self._server is None:
            return None
        return f'http://{self._host}:{self._server.server_address[1]}'

    def run(self):
        try:
            # create_app() does DB create/seed/enrich — keep it off the GUI thread
            app = self._factory()

            last_err: Optional[Exception] = None
            for port in self._ports:
                try:
                    self._server = _ExclusiveServer(self._host, port, app)
                    break
                except (OSError, SystemExit) as e:
                    # werkzeug prints a hint and calls sys.exit(1) on EADDRINUSE;
                    # inside a QThread that would abort the whole process.
                    last_err = e
                    continue
            if self._server is None:
                raise OSError(f'No free port among {self._ports}: {last_err}')

            self.server_ready.emit(self.url)
            self._server.serve_forever()
        except (Exception, SystemExit) as e:  # noqa: BLE001 — surface anything to the UI
            self.server_error.emit(str(e) or repr(e))

    def stop(self):
        """Shut the server down. Safe to call from the GUI thread."""
        server, self._server = self._server, None
        if server is not None:
            try:
                server.shutdown()
                server.server_close()
            except Exception:  # noqa: BLE001
                pass
        self.wait(3000)
