from pathlib import Path
from flask import Flask
from config import Config
from .extensions import db, login_manager, migrate

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    from . import models
    from .auth import bp as auth_bp
    from .main import bp as main_bp
    from .groups import bp as groups_bp
    from .expenses import bp as expenses_bp
    from .settlements import bp as settlements_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(groups_bp, url_prefix="/groups")
    app.register_blueprint(expenses_bp, url_prefix="/expenses")
    app.register_blueprint(settlements_bp, url_prefix="/settlements")

    with app.app_context():
        db.create_all()

    return app
