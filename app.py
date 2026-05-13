import os
import secrets
from datetime import timedelta

from flask import Flask, redirect, render_template, session, url_for
from flask_login import LoginManager, current_user

from auth import auth_bp
from dashboard import dashboard_bp
from models import User, db, ensure_schema, seed_admin


def create_app():
    app = Flask(__name__)
    base_dir = os.path.abspath(os.path.dirname(__file__))

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", secrets.token_hex(32))
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(base_dir, "database", "company_dashboard.db"),
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = os.path.join(base_dir, "uploads")
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(os.path.join(base_dir, "database"), exist_ok=True)

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "warning"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.context_processor
    def inject_globals():
        if "_csrf_token" not in session:
            session["_csrf_token"] = secrets.token_urlsafe(32)
        return {
            "csrf_token": session["_csrf_token"],
            "current_user": current_user,
        }

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)

    with app.app_context():
        db.create_all()
        ensure_schema()
        seed_admin()

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard.dashboard"))
        return redirect(url_for("auth.login"))

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("error.html", code=403, message="Access denied"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", code=404, message="Page not found"), 404

    @app.errorhandler(413)
    def file_too_large(_error):
        return render_template("error.html", code=413, message="Uploaded file is too large"), 413

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
