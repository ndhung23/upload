import os
from datetime import datetime

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, inspect, or_, text
from werkzeug.utils import secure_filename

from auth import role_required
from etl import ETLError, process_excel
from export_service import build_export_workbook
from models import (
    DimCarMaker,
    DimCountry,
    DimCountryOfMaker,
    DimCustomer,
    DimLaser,
    DimMarket,
    DimType,
    DimType2,
    FactETD,
    UploadLog,
    User,
    db,
)


dashboard_bp = Blueprint("dashboard", __name__)

TABLE_REGISTRY = {
    "FACT_ETD": FactETD,
    "DIM_Customer": DimCustomer,
    "DIM_Type": DimType,
    "DIM_Laser": DimLaser,
    "DIM_CountryOfMaker": DimCountryOfMaker,
    "DIM_Country": DimCountry,
    "DIM_CarMaker": DimCarMaker,
    "DIM_Market": DimMarket,
    "DIM_Type2": DimType2,
    "users": User,
    "UPLOAD_LOGS": UploadLog,
}

FORBIDDEN_SQL = ("UPDATE", "DELETE", "DROP", "INSERT", "ALTER", "CREATE", "REPLACE", "TRUNCATE", "PRAGMA", "ATTACH", "DETACH")

MONTH_ORDER = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


def _month_key(month):
    try:
        year, name = month.split("-")
        return int(year) * 12 + MONTH_ORDER[name]
    except Exception:
        return 999999


def _allowed_months(month_from=None, month_to=None):
    months = [m[0] for m in db.session.query(FactETD.Month).distinct().all()]
    months = sorted(months, key=_month_key)
    if not month_from and not month_to:
        return months

    start = _month_key(month_from) if month_from else -1
    end = _month_key(month_to) if month_to else 999999
    return [month for month in months if start <= _month_key(month) <= end]


def _base_query():
    return (
        db.session.query(FactETD)
        .join(DimCustomer, FactETD.CustomerID == DimCustomer.CustomerID)
        .join(DimType, FactETD.TypeID == DimType.TypeID)
        .join(DimCountry, FactETD.CountryID == DimCountry.CountryID)
        .join(DimCarMaker, FactETD.CarMakerID == DimCarMaker.CarMakerID)
        .join(DimMarket, FactETD.MarketID == DimMarket.MarketID)
    )


def _apply_filters(query):
    customer_id = request.args.get("customer_id")
    type_id = request.args.get("type_id")
    country_id = request.args.get("country_id")
    car_maker_id = request.args.get("car_maker_id")
    market_id = request.args.get("market_id")
    month_from = request.args.get("month_from")
    month_to = request.args.get("month_to")

    if customer_id:
        query = query.filter(FactETD.CustomerID == int(customer_id))
    if type_id:
        query = query.filter(FactETD.TypeID == int(type_id))
    if country_id:
        query = query.filter(FactETD.CountryID == int(country_id))
    if car_maker_id:
        query = query.filter(FactETD.CarMakerID == int(car_maker_id))
    if market_id:
        query = query.filter(FactETD.MarketID == int(market_id))

    month_labels = _allowed_months(month_from, month_to)
    if month_from or month_to:
        query = query.filter(FactETD.Month.in_(month_labels or ["__none__"]))

    return query


def _serialize_value(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value


def _model_columns(model):
    return [column.name for column in model.__table__.columns]


def _serialize_model(row, columns):
    return {column: _serialize_value(getattr(row, column)) for column in columns}


def _create_upload_log(filename, status, message="", result=None):
    log = UploadLog(
        filename=filename,
        uploaded_by=current_user.username,
        status=status,
        message=message or "",
        total_rows=getattr(result, "total_rows", 0) if result else 0,
        inserted_rows=getattr(result, "inserted", 0) if result else 0,
        updated_rows=getattr(result, "updated", 0) if result else 0,
        skipped_rows=getattr(result, "skipped", 0) if result else 0,
        invalid_rows=getattr(result, "invalid_rows", 0) if result else 0,
    )
    db.session.add(log)
    db.session.commit()
    return log


def _validate_select_sql(sql):
    normalized = sql.strip().rstrip(";").strip()
    upper = normalized.upper()
    if not upper.startswith("SELECT"):
        return None, "Only SELECT statements are allowed"
    if ";" in normalized:
        return None, "Multiple SQL statements are not allowed"
    padded = f" {upper} "
    for keyword in FORBIDDEN_SQL:
        if f" {keyword} " in padded:
            return None, f"{keyword} is not allowed"
    return normalized, None


@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


@dashboard_bp.route("/upload")
@role_required("Admin", "Manager")
def upload_page():
    return render_template("upload.html")


@dashboard_bp.route("/upload-history")
@role_required("Admin", "Manager")
def upload_history():
    return render_template("upload_history.html")


@dashboard_bp.route("/admin/data-explorer")
@role_required("Admin")
def data_explorer():
    return render_template("data_explorer.html", tables=list(TABLE_REGISTRY.keys()))


@dashboard_bp.route("/api/filter")
@login_required
def api_filter():
    return jsonify(
        {
            "customers": [
                {"id": row.CustomerID, "text": row.Customer}
                for row in DimCustomer.query.order_by(DimCustomer.Customer).all()
            ],
            "types": [
                {"id": row.TypeID, "text": row.Type}
                for row in DimType.query.order_by(DimType.Type).all()
            ],
            "countries": [
                {"id": row.CountryID, "text": row.Country}
                for row in DimCountry.query.order_by(DimCountry.Country).all()
            ],
            "car_makers": [
                {"id": row.CarMakerID, "text": row.CarMaker}
                for row in DimCarMaker.query.order_by(DimCarMaker.CarMaker).all()
            ],
            "markets": [
                {"id": row.MarketID, "text": row.Market}
                for row in DimMarket.query.order_by(DimMarket.Market).all()
            ],
            "months": _allowed_months(),
        }
    )


@dashboard_bp.route("/api/dashboard")
@login_required
def api_dashboard():
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(max(request.args.get("per_page", 25, type=int), 5), 100)

    filtered = _apply_filters(_base_query())

    total_value = filtered.with_entities(func.coalesce(func.sum(FactETD.Value), 0)).scalar() or 0
    total_part_no = filtered.with_entities(func.count(func.distinct(FactETD.PartNo))).scalar() or 0
    total_customer = filtered.with_entities(func.count(func.distinct(FactETD.CustomerID))).scalar() or 0
    total_market = filtered.with_entities(func.count(func.distinct(FactETD.MarketID))).scalar() or 0

    chart_rows = (
        filtered.with_entities(FactETD.Month, func.sum(FactETD.Value).label("total"))
        .group_by(FactETD.Month)
        .all()
    )
    chart_rows = sorted(chart_rows, key=lambda item: _month_key(item.Month))

    top_customer = (
        filtered.with_entities(DimCustomer.Customer, func.sum(FactETD.Value).label("total"))
        .group_by(DimCustomer.Customer)
        .order_by(func.sum(FactETD.Value).desc())
        .first()
    )
    top_market = (
        filtered.with_entities(DimMarket.Market, func.sum(FactETD.Value).label("total"))
        .group_by(DimMarket.Market)
        .order_by(func.sum(FactETD.Value).desc())
        .first()
    )

    table_query = filtered.order_by(FactETD.PartNo.asc(), FactETD.Month.asc())
    pagination = table_query.paginate(page=page, per_page=per_page, error_out=False)
    rows = [
        {
            "PartNo": item.PartNo,
            "Customer": item.customer.Customer,
            "Type": item.type.Type,
            "Country": item.country.Country,
            "CarMaker": item.car_maker.CarMaker,
            "Market": item.market.Market,
            "Month": item.Month,
            "Value": item.Value,
        }
        for item in pagination.items
    ]

    return jsonify(
        {
            "stats": {
                "total_value": total_value,
                "total_part_no": total_part_no,
                "total_customer": total_customer,
                "total_market": total_market,
                "top_customer": top_customer.Customer if top_customer else "-",
                "top_market": top_market.Market if top_market else "-",
            },
            "chart": {
                "months": [row.Month for row in chart_rows],
                "values": [float(row.total or 0) for row in chart_rows],
            },
            "table": {
                "rows": rows,
                "page": pagination.page,
                "pages": pagination.pages,
                "total": pagination.total,
                "per_page": per_page,
            },
        }
    )


@dashboard_bp.route("/api/upload", methods=["POST"])
@role_required("Admin", "Manager")
def api_upload():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "message": "Please choose an Excel file"}), 400

    filename = secure_filename(file.filename)
    if not filename.lower().endswith((".xlsx", ".xlsm", ".xls")):
        return jsonify({"ok": False, "message": "Only Excel files are allowed"}), 400

    stamped = datetime.now().strftime("%Y%m%d_%H%M%S_") + filename
    file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], stamped)
    file.save(file_path)

    try:
        result = process_excel(file_path)
    except ETLError as exc:
        _create_upload_log(filename, "fail", str(exc))
        return jsonify({"ok": False, "message": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        _create_upload_log(filename, "fail", str(exc))
        return jsonify({"ok": False, "message": "Unexpected import error: " + str(exc)}), 500

    _create_upload_log(filename, "success", "Upload completed", result)
    return jsonify(
        {
            "ok": True,
            "message": (
                f"Imported {result.inserted} new facts, updated {result.updated}, "
                f"skipped {result.skipped}, invalid {result.invalid_rows}. "
                f"New dimensions: {result.dim_inserted}."
            ),
            "result": result.__dict__,
        }
    )


@dashboard_bp.route("/upload", methods=["POST"])
@role_required("Admin", "Manager")
def upload_form():
    response = api_upload()
    payload = response[0].get_json() if isinstance(response, tuple) else response.get_json()
    flash(payload["message"], "success" if payload.get("ok") else "danger")
    return redirect(url_for("dashboard.upload_page"))


@dashboard_bp.route("/api/export")
@role_required("Admin", "Manager")
def api_export():
    output = build_export_workbook()
    return send_file(
        output,
        as_attachment=True,
        download_name="company_dashboard_export.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@dashboard_bp.route("/api/upload-logs")
@role_required("Admin", "Manager")
def api_upload_logs():
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(max(request.args.get("per_page", 25, type=int), 5), 100)
    query = UploadLog.query.order_by(UploadLog.uploaded_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    columns = _model_columns(UploadLog)
    return jsonify(
        {
            "columns": columns,
            "rows": [_serialize_model(row, columns) for row in pagination.items],
            "page": pagination.page,
            "pages": pagination.pages,
            "total": pagination.total,
        }
    )


@dashboard_bp.route("/api/admin/tables")
@role_required("Admin")
def api_admin_tables():
    return jsonify({"tables": list(TABLE_REGISTRY.keys())})


@dashboard_bp.route("/api/admin/table-data")
@role_required("Admin")
def api_admin_table_data():
    table = request.args.get("table", "FACT_ETD")
    model = TABLE_REGISTRY.get(table)
    if not model:
        return jsonify({"ok": False, "message": "Unknown table"}), 404

    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(max(request.args.get("per_page", 25, type=int), 5), 200)
    search = request.args.get("search", "").strip()
    sort_col = request.args.get("sort_col", "")
    sort_dir = request.args.get("sort_dir", "asc")
    columns = _model_columns(model)

    query = model.query
    if table == "FACT_ETD":
        month = request.args.get("month", "").strip()
        customer_id = request.args.get("customer_id", type=int)
        market_id = request.args.get("market_id", type=int)
        if month:
            query = query.filter(FactETD.Month == month)
        if customer_id:
            query = query.filter(FactETD.CustomerID == customer_id)
        if market_id:
            query = query.filter(FactETD.MarketID == market_id)
    elif search:
        filters = []
        for column in model.__table__.columns:
            if str(column.type).upper().startswith(("VARCHAR", "TEXT")):
                filters.append(getattr(model, column.name).ilike(f"%{search}%"))
        if filters:
            query = query.filter(or_(*filters))

    if sort_col in columns:
        sort_attr = getattr(model, sort_col)
        query = query.order_by(sort_attr.desc() if sort_dir == "desc" else sort_attr.asc())
    else:
        query = query.order_by(getattr(model, columns[0]).asc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify(
        {
            "ok": True,
            "table": table,
            "columns": columns,
            "rows": [_serialize_model(row, columns) for row in pagination.items],
            "page": pagination.page,
            "pages": pagination.pages,
            "total": pagination.total,
        }
    )


@dashboard_bp.route("/api/admin/sql", methods=["POST"])
@role_required("Admin")
def api_admin_sql():
    payload = request.get_json(silent=True) or {}
    sql, error = _validate_select_sql(payload.get("sql", ""))
    if error:
        return jsonify({"ok": False, "message": error}), 400

    try:
        result = db.session.execute(text(sql))
        rows = result.mappings().fetchmany(500)
        columns = list(result.keys())
    except Exception as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400

    return jsonify(
        {
            "ok": True,
            "columns": columns,
            "rows": [{key: _serialize_value(value) for key, value in row.items()} for row in rows],
            "total": len(rows),
            "limited_to": 500,
        }
    )
