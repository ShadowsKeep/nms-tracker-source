import os
import sys
from pathlib import Path
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def get_data_dir() -> Path:
    """Persistent user data directory (save file + WebEngine cache)."""
    if getattr(sys, 'frozen', False):
        local = os.environ.get('LOCALAPPDATA') or str(Path.home() / 'AppData' / 'Local')
        data_dir = Path(local) / 'ShadowskeepLLC' / 'NMSTracker'
    else:
        data_dir = Path(__file__).parent.parent / 'instance'
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_resource_path(relative_path: str) -> str:
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS) / 'app'  # type: ignore[attr-defined]
    else:
        base = Path(__file__).parent
    return str(base / relative_path)


def _migrate_schema():
    """Tiny forward-only migrations for existing databases."""
    from sqlalchemy import inspect, text
    cols = {c['name'] for c in inspect(db.engine).get_columns('ships')}
    if 'save_key' not in cols:
        with db.engine.begin() as conn:
            conn.execute(text('ALTER TABLE ships ADD COLUMN save_key VARCHAR(400)'))


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=get_resource_path('templates'),
        static_folder=get_resource_path('static'),
    )
    db_path = get_data_dir() / 'nms-tracker.db'
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.urandom(24)

    db.init_app(app)
    with app.app_context():
        from app import models  # noqa: F401
        db.create_all()
        _migrate_schema()
        from app.gamedata import game
        game()  # load + index once at startup so the first page is fast

    from app.routes.pages import pages_bp
    from app.routes.api import api_bp
    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)
    return app
