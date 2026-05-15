from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from models import User, db


auth_bp = Blueprint("auth", __name__)


ROLES = ("Admin", "Manager", "Staff")


def validate_csrf():
    token = request.form.get("_csrf_token") or request.headers.get("X-CSRFToken")
    return token and token == session.get("_csrf_token")


def csrf_protect():
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not validate_csrf():
        abort(403)


def role_required(*roles):
    def decorator(func):
        @wraps(func)
        @login_required
        def wrapper(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return func(*args, **kwargs)

        return wrapper

    return decorator


@auth_bp.before_app_request
def before_request():
    csrf_protect()


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        password_ok = user and (
            (user.password_plain and user.password_plain == password)
            or check_password_hash(user.password_hash, password)
        )
        if user and user.is_active and password_ok:
            login_user(user)
            return redirect(url_for("dashboard.dashboard"))
        flash("Invalid username or password", "danger")

    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Logged out", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/users")
@role_required("Admin")
def users():
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(max(request.args.get("per_page", 10, type=int), 5), 50)
    search = request.args.get("search", "").strip()
    role = request.args.get("role", "").strip()
    gender = request.args.get("gender", "").strip()
    status = request.args.get("status", "").strip()

    query = User.query
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            (User.username.ilike(pattern))
            | (User.full_name.ilike(pattern))
            | (User.employee_code.ilike(pattern))
        )
    if role in ROLES:
        query = query.filter(User.role == role)
    if gender:
        query = query.filter(User.gender == gender)
    if status == "active":
        query = query.filter(User.is_active.is_(True))
    elif status == "inactive":
        query = query.filter(User.is_active.is_(False))

    pagination = query.order_by(User.username.asc()).paginate(page=page, per_page=per_page, error_out=False)
    rows = pagination.items
    managers = User.query.filter(User.role.in_(["Admin", "Manager"]), User.is_active.is_(True)).order_by(User.username.asc()).all()
    return render_template(
        "users.html",
        users=rows,
        roles=ROLES,
        managers=managers,
        pagination=pagination,
        filters={"search": search, "role": role, "gender": gender, "status": status, "per_page": per_page},
        genders=["Male", "Female", "Other"],
    )


@auth_bp.route("/users/create", methods=["POST"])
@role_required("Admin")
def create_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    full_name = request.form.get("full_name", "").strip()
    employee_code = request.form.get("employee_code", "").strip()
    role = request.form.get("role", "Staff")
    gender = request.form.get("gender", "").strip()
    manager_id = request.form.get("manager_id", type=int)

    if not username or not password or role not in ROLES:
        flash("Username, password and role are required", "danger")
        return redirect(url_for("auth.users"))
    if User.query.filter_by(username=username).first():
        flash("Username already exists", "warning")
        return redirect(url_for("auth.users"))

    db.session.add(
        User(
            username=username,
            password_hash=generate_password_hash(password),
            password_plain=password,
            full_name=full_name,
            employee_code=employee_code,
            role=role,
            gender=gender,
            manager_id=manager_id if manager_id else None,
            is_active=True,
        )
    )
    db.session.commit()
    flash("User created", "success")
    return redirect(url_for("auth.users"))


@auth_bp.route("/users/<int:user_id>/update", methods=["POST"])
@role_required("Admin")
def update_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)

    role = request.form.get("role", user.role)
    if role not in ROLES:
        flash("Invalid role", "danger")
        return redirect(url_for("auth.users"))

    user.role = role
    user.full_name = request.form.get("full_name", "").strip()
    user.employee_code = request.form.get("employee_code", "").strip()
    user.gender = request.form.get("gender", "").strip()
    manager_id = request.form.get("manager_id", type=int)
    user.manager_id = manager_id if manager_id and manager_id != user.id else None
    user.is_active = request.form.get("is_active") == "on"
    password = request.form.get("password", "")
    if password:
        user.password_hash = generate_password_hash(password)
        user.password_plain = password
    db.session.commit()
    flash("User updated", "success")
    return redirect(url_for("auth.users"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not check_password_hash(current_user.password_hash, current_password):
            flash("Current password is incorrect", "danger")
            return redirect(url_for("auth.change_password"))
        if len(new_password) < 3:
            flash("New password must be at least 3 characters", "danger")
            return redirect(url_for("auth.change_password"))
        if new_password != confirm_password:
            flash("Password confirmation does not match", "danger")
            return redirect(url_for("auth.change_password"))

        current_user.password_hash = generate_password_hash(new_password)
        current_user.password_plain = new_password
        db.session.commit()
        flash("Password changed successfully", "success")
        return redirect(url_for("dashboard.dashboard"))

    return render_template("change_password.html")


@auth_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@role_required("Admin")
def delete_user(user_id):
    if user_id == current_user.id:
        flash("You cannot delete your own account", "warning")
        return redirect(url_for("auth.users"))

    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    db.session.delete(user)
    db.session.commit()
    flash("User deleted", "success")
    return redirect(url_for("auth.users"))
