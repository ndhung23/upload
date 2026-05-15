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
    DataChangeLog,
    FactETD,
    UploadLog,
    User,
    db,
)


dashboard_bp = Blueprint("dashboard", __name__)

FILE_CATEGORIES = {
    "AP": "AP",
    "FC1": "FC1",
    "FC2": "FC2",
    "AP_LAST_YEAR": "AP last year",
    "ACTUAL_LAST_YEAR": "Actual last year",
}
DEFAULT_MONTH_TO = "26-Mar"

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
    "DATA_CHANGE_LOGS": DataChangeLog,
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
MONTH_NAMES_BY_NUMBER = {value: key for key, value in MONTH_ORDER.items()}


def _month_key(month):
    try:
        year, name = month.split("-")
        return int(year) * 12 + MONTH_ORDER[name]
    except Exception:
        return 999999


def _month_label_from_key(key):
    year = key // 12
    month_number = key % 12
    if month_number == 0:
        year -= 1
        month_number = 12
    return f"{year % 100:02d}-{MONTH_NAMES_BY_NUMBER[month_number]}"


def _all_months(query=None):
    source = query if query is not None else db.session.query(FactETD.Month)
    months = [m[0] for m in source.distinct().all()]
    return sorted(months, key=_month_key)


def _fy_bounds(fiscal_year):
    if not fiscal_year:
        return None, None
    value = str(fiscal_year).upper().replace("FY", "").strip()
    if not value.isdigit():
        return None, None
    year = int(value) % 100
    return f"{year:02d}-Apr", f"{(year + 1) % 100:02d}-May"


def _fy_label_for_month(month):
    try:
        year_text, name = month.split("-")
        year = int(year_text)
        fiscal_year = year if MONTH_ORDER[name] >= 4 else year - 1
        return f"FY{fiscal_year % 100:02d}"
    except Exception:
        return None


def _allowed_months(month_from=None, month_to=None, fiscal_year=None, query=None):
    months = _all_months(query)
    months = sorted(months, key=_month_key)
    fy_from, fy_to = _fy_bounds(fiscal_year)
    month_from = month_from or fy_from
    month_to = month_to or fy_to
    if not month_from and not month_to:
        return months

    start = _month_key(month_from) if month_from else -1
    end = _month_key(month_to) if month_to else 999999
    return [month for month in months if start <= _month_key(month) <= end]


def _data_months():
    months = _allowed_months()
    if not months:
        return months
    max_key = max(_month_key(month) for month in months)
    extended = set(months)
    for offset in range(1, 13):
        extended.add(_month_label_from_key(max_key + offset))
    return sorted(extended, key=_month_key)


def _data_allowed_months(month_from=None, month_to=None, fiscal_year=None):
    months = _data_months()
    fy_from, fy_to = _fy_bounds(fiscal_year)
    month_from = month_from or fy_from
    month_to = month_to or fy_to
    if not month_from and not month_to:
        return months
    start = _month_key(month_from) if month_from else -1
    end = _month_key(month_to) if month_to else 999999
    return [month for month in months if start <= _month_key(month) <= end]


def _base_query():
    return (
        db.session.query(FactETD)
        .join(UploadLog, FactETD.UploadLogID == UploadLog.id)
        .join(DimCustomer, FactETD.CustomerID == DimCustomer.CustomerID)
        .join(DimType, FactETD.TypeID == DimType.TypeID)
        .join(DimType2, FactETD.Type2ID == DimType2.Type2ID)
        .join(DimCountry, FactETD.CountryID == DimCountry.CountryID)
        .join(DimCarMaker, FactETD.CarMakerID == DimCarMaker.CarMakerID)
        .join(DimMarket, FactETD.MarketID == DimMarket.MarketID)
        .filter(UploadLog.status == "success")
    )


def _apply_filters(query, upload_log_id=None, include_upload=True):
    if upload_log_id is None and include_upload:
        upload_log_id = request.args.get("upload_log_id", type=int)
    customer_id = request.args.get("customer_id")
    type_id = request.args.get("type_id")
    type2_id = request.args.get("type2_id")
    file_ids = request.args.get("file_ids")
    country_id = request.args.get("country_id")
    car_maker_id = request.args.get("car_maker_id")
    market_id = request.args.get("market_id")
    month_from = request.args.get("month_from")
    month_to = request.args.get("month_to")
    fiscal_year = request.args.get("fiscal_year")

    if upload_log_id:
        query = query.filter(FactETD.UploadLogID == upload_log_id)
    if file_ids:
        file_id_list = [int(id.strip()) for id in file_ids.split(",") if id.strip().isdigit()]
        if file_id_list:
            query = query.filter(FactETD.UploadLogID.in_(file_id_list))
    if customer_id:
        query = query.filter(FactETD.CustomerID == int(customer_id))
    if type_id:
        query = query.filter(FactETD.TypeID == int(type_id))
    if type2_id:
        query = query.filter(FactETD.Type2ID == int(type2_id))
    if country_id:
        query = query.filter(FactETD.CountryID == int(country_id))
    if car_maker_id:
        query = query.filter(FactETD.CarMakerID == int(car_maker_id))
    if market_id:
        query = query.filter(FactETD.MarketID == int(market_id))

    month_labels = _allowed_months(month_from, month_to, fiscal_year)
    if month_from or month_to or fiscal_year:
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


def _primary_key_column(model):
    return list(model.__table__.primary_key.columns)[0]


def _coerce_column_value(column, value):
    if value == "":
        return None if column.nullable else ""
    type_name = column.type.__class__.__name__.lower()
    if "integer" in type_name:
        return int(value)
    if "float" in type_name or "numeric" in type_name:
        return float(value)
    if "boolean" in type_name:
        return str(value).lower() in {"1", "true", "on", "yes"}
    return value


def _apply_payload_to_model(row, model, payload):
    changed = {}
    for column in model.__table__.columns:
        if column.primary_key or column.name not in payload:
            continue
        value = _coerce_column_value(column, payload[column.name])
        if getattr(row, column.name) != value:
            changed[column.name] = {"old": _serialize_value(getattr(row, column.name)), "new": _serialize_value(value)}
            setattr(row, column.name, value)
    if isinstance(row, FactETD):
        row.updated_by = current_user.username
        row.updated_at = datetime.utcnow()
    return changed


def _record_data_change(table_name, row_id, action, detail):
    db.session.add(
        DataChangeLog(
            table_name=table_name,
            row_id=str(row_id or ""),
            action=action,
            changed_by=current_user.username,
            detail=detail or "",
        )
    )


def _create_upload_log(filename, stored_filename, file_category, status, message="", result=None):
    log = UploadLog(
        filename=filename,
        stored_filename=stored_filename,
        file_category=file_category,
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


def _update_upload_log(log, status, message="", result=None):
    log.status = status
    log.message = message or ""
    if result:
        log.total_rows = result.total_rows
        log.inserted_rows = result.inserted
        log.updated_rows = result.updated
        log.skipped_rows = result.skipped
        log.invalid_rows = result.invalid_rows
    db.session.commit()
    return log


def _successful_upload_options():
    return (
        UploadLog.query.filter(UploadLog.status == "success")
        .order_by(UploadLog.uploaded_at.desc(), UploadLog.id.desc())
        .all()
    )


def _upload_label(log):
    prefix = FILE_CATEGORIES.get(log.file_category, log.file_category)
    return f"{prefix} - #{log.id} - {log.filename}" if prefix else f"#{log.id} - {log.filename}"


def _default_month_labels():
    months = _all_months(_base_query().with_entities(FactETD.Month))
    return [month for month in months if _month_key(month) <= _month_key(DEFAULT_MONTH_TO)]


def _chart_group_field(group_by):
    if group_by == "customer":
        return DimCustomer.Customer
    if group_by == "type2":
        return DimType2.Type2
    if group_by == "country":
        return DimCountry.Country
    if group_by == "car_maker":
        return DimCarMaker.CarMaker
    if group_by == "market":
        return DimMarket.Market
    if group_by == "file":
        return UploadLog.file_category
    if group_by == "type":
        return DimType.Type
    return DimType2.Type2


def _category_label(value):
    return FILE_CATEGORIES.get(value, value or "(blank)")


def _fact_display_row(item):
    return {
        "ID": item.ID,
        "PartNo": item.PartNo,
        "CustomerID": item.CustomerID,
        "Customer": item.customer.Customer,
        "TypeID": item.TypeID,
        "Type": item.type.Type,
        "Type2ID": item.Type2ID,
        "Type2": item.type2.Type2,
        "LaserID": item.LaserID,
        "Laser": item.laser.Laser,
        "CountryOfMakerID": item.CountryOfMakerID,
        "CountryOfMaker": item.country_of_maker.CountryOfMaker,
        "CarMakerID": item.CarMakerID,
        "CarMaker": item.car_maker.CarMaker,
        "CountryID": item.CountryID,
        "Country": item.country.Country,
        "MarketID": item.MarketID,
        "Market": item.market.Market,
        "Month": item.Month,
        "Value": item.Value,
        "UploadLogID": item.UploadLogID,
        "File": _upload_label(item.upload_log),
        "updated_by": item.updated_by,
        "updated_at": _serialize_value(item.updated_at),
    }


def _stored_upload_path(log):
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    if log.stored_filename:
        path = os.path.abspath(os.path.join(upload_folder, log.stored_filename))
        upload_root = os.path.abspath(upload_folder)
        if path.startswith(upload_root) and os.path.exists(path):
            return path
        return None

    candidates = (
        name for name in os.listdir(upload_folder)
        if name.endswith(log.filename)
    )
    for name in candidates:
        path = os.path.abspath(os.path.join(upload_folder, name))
        upload_root = os.path.abspath(upload_folder)
        if path.startswith(upload_root) and os.path.exists(path):
            return path
    return None


def _delete_stored_upload_file(log):
    path = _stored_upload_path(log)
    if not path:
        log.stored_filename = "__deleted__"
        return False
    os.remove(path)
    log.stored_filename = "__deleted__"
    return True


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
    return render_template("upload.html", file_categories=FILE_CATEGORIES)


@dashboard_bp.route("/upload-history")
@role_required("Admin", "Manager")
def upload_history():
    return render_template("upload_history.html")


@dashboard_bp.route("/admin/data-explorer")
@role_required("Admin", "Manager", "Staff")
def data_explorer():
    return render_template("data_explorer.html", tables=list(TABLE_REGISTRY.keys()))


@dashboard_bp.route("/api/filter")
@login_required
def api_filter():
    months = _allowed_months()
    fiscal_years = sorted({label for label in (_fy_label_for_month(month) for month in months) if label}, reverse=True)
    uploads = _successful_upload_options()
    
    return jsonify(
        {
            "uploads": [{"id": row.id, "text": _upload_label(row), "category": row.file_category} for row in uploads],
            "file_categories": [{"id": key, "text": value} for key, value in FILE_CATEGORIES.items()],
            "fiscal_years": fiscal_years,
            "customers": [
                {"id": row.CustomerID, "text": row.Customer}
                for row in DimCustomer.query.order_by(DimCustomer.Customer).all()
            ],
            "types": [
                {"id": row.TypeID, "text": row.Type}
                for row in DimType.query.order_by(DimType.Type).all()
            ],
            "type2s": [
                {"id": row.Type2ID, "text": row.Type2}
                for row in DimType2.query.order_by(DimType2.Type2).all()
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
            "months": months,
        }
    )


@dashboard_bp.route("/api/dashboard")
@login_required
def api_dashboard():
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(max(request.args.get("per_page", 25, type=int), 5), 100)
    chart_type = request.args.get("chart_type", "bar")
    chart_group = request.args.get("chart_group", "").strip()
    if chart_type != "bar" and not chart_group:
        chart_group = "customer"
    compare_upload_id = request.args.get("compare_upload_id", type=int)
    has_explicit_month = bool(request.args.get("month_from") or request.args.get("month_to") or request.args.get("fiscal_year"))
    has_file_filter = bool(request.args.get("upload_log_id") or request.args.get("file_category"))

    filtered = _apply_filters(_base_query())
    if not has_explicit_month:
        filtered = filtered.filter(FactETD.Month.in_(_default_month_labels() or ["__none__"]))

    total_value = filtered.with_entities(func.coalesce(func.sum(FactETD.Value), 0)).scalar() or 0
    total_part_no = filtered.with_entities(func.count(func.distinct(FactETD.PartNo))).scalar() or 0
    total_customer = filtered.with_entities(func.count(func.distinct(FactETD.CustomerID))).scalar() or 0
    total_market = filtered.with_entities(func.count(func.distinct(FactETD.MarketID))).scalar() or 0

    monthly_rows = (
        filtered.with_entities(FactETD.Month, func.sum(FactETD.Value).label("total"))
        .group_by(FactETD.Month)
        .all()
    )
    monthly_rows = sorted(monthly_rows, key=lambda item: _month_key(item.Month))

    group_field = _chart_group_field(chart_group or "type2")
    type_rows = (
        filtered.with_entities(group_field.label("label"), func.sum(FactETD.Value).label("total"))
        .group_by(group_field)
        .order_by(func.sum(FactETD.Value).desc())
        .all()
    )
    stacked_rows = (
        filtered.with_entities(FactETD.Month, group_field.label("label"), func.sum(FactETD.Value).label("total"))
        .group_by(FactETD.Month, group_field)
        .all()
    )
    stacked_months = sorted({row.Month for row in stacked_rows}, key=_month_key)
    stacked_types = [row.label for row in type_rows]
    stacked_lookup = {(row.Month, row.label): float(row.total or 0) for row in stacked_rows}

    default_series = []
    default_month_axis = _default_month_labels()
    if not has_file_filter and chart_type == "bar" and not chart_group:
        default_month_axis = [row.Month for row in monthly_rows] if has_explicit_month else _default_month_labels()
        for key, label in FILE_CATEGORIES.items():
            rows_for_category = (
                filtered.filter(UploadLog.file_category == key)
                .with_entities(FactETD.Month, func.sum(FactETD.Value).label("total"))
                .group_by(FactETD.Month)
                .all()
            )
            lookup = {row.Month: float(row.total or 0) for row in rows_for_category}
            default_series.append({"name": label, "values": [lookup.get(month, 0) for month in default_month_axis]})

    compare_chart = None
    if compare_upload_id:
        compare_query = _apply_filters(_base_query(), upload_log_id=compare_upload_id)
        compare_rows = (
            compare_query.with_entities(FactETD.Month, func.sum(FactETD.Value).label("total"))
            .group_by(FactETD.Month)
            .all()
        )
        compare_rows = sorted(compare_rows, key=lambda item: _month_key(item.Month))
        compare_chart = {
            "months": [row.Month for row in compare_rows],
            "values": [float(row.total or 0) for row in compare_rows],
        }

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
            "Type2": item.type2.Type2,
            "Country": item.country.Country,
            "CarMaker": item.car_maker.CarMaker,
            "Market": item.market.Market,
            "File": FILE_CATEGORIES.get(item.upload_log.file_category, item.upload_log.file_category),
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
                "type": chart_type,
                "group": chart_group,
                "months": [row.Month for row in monthly_rows],
                "values": [float(row.total or 0) for row in monthly_rows],
                "default_months": default_month_axis,
                "default_series": default_series,
                "pie_labels": [_category_label(row.label) for row in type_rows],
                "pie_values": [float(row.total or 0) for row in type_rows],
                "stacked_months": stacked_months,
                "stacked_series": [
                    {
                        "name": _category_label(item),
                        "values": [stacked_lookup.get((month, item), 0) for month in stacked_months],
                    }
                    for item in stacked_types
                ],
                "compare": compare_chart,
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
    file_category = request.form.get("file_category", "").strip()
    if file_category not in FILE_CATEGORIES:
        return jsonify({"ok": False, "message": "Please choose a file type before uploading"}), 400

    stamped = datetime.now().strftime("%Y%m%d_%H%M%S_") + filename
    file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], stamped)
    file.save(file_path)
    log = _create_upload_log(filename, stamped, file_category, "processing", "Upload saved, import is running")

    try:
        result = process_excel(file_path, upload_log_id=log.id, actor=current_user.username)
    except ETLError as exc:
        _update_upload_log(log, "fail", str(exc))
        return jsonify({"ok": False, "message": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        _update_upload_log(log, "fail", str(exc))
        return jsonify({"ok": False, "message": "Unexpected import error: " + str(exc)}), 500

    _update_upload_log(log, "success", "Upload completed", result)
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
    rows = []
    for row in pagination.items:
        payload = _serialize_model(row, columns)
        payload["download_url"] = url_for("dashboard.download_upload", log_id=row.id) if _stored_upload_path(row) else ""
        rows.append(payload)
    return jsonify(
        {
            "columns": columns,
            "rows": rows,
            "page": pagination.page,
            "pages": pagination.pages,
            "total": pagination.total,
        }
    )


@dashboard_bp.route("/upload-history/<int:log_id>/download")
@role_required("Admin", "Manager")
def download_upload(log_id):
    log = db.session.get(UploadLog, log_id)
    if not log:
        flash("Uploaded file was not found in history", "warning")
        return redirect(url_for("dashboard.upload_history"))
    path = _stored_upload_path(log)
    if not path:
        flash("Stored Excel file is missing from uploads folder", "warning")
        return redirect(url_for("dashboard.upload_history"))
    return send_file(
        path,
        as_attachment=True,
        download_name=log.filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@dashboard_bp.route("/api/upload-logs/<int:log_id>", methods=["POST"])
@role_required("Admin", "Manager")
def update_upload_log(log_id):
    log = db.session.get(UploadLog, log_id)
    if not log:
        return jsonify({"ok": False, "message": "Upload log was not found"}), 404

    payload = request.get_json(silent=True) or {}
    filename = (payload.get("filename") or "").strip()
    if not filename:
        return jsonify({"ok": False, "message": "Filename is required"}), 400
    if not secure_filename(filename).lower().endswith((".xlsx", ".xlsm", ".xls")):
        return jsonify({"ok": False, "message": "Filename must be an Excel file name"}), 400

    log.filename = filename
    db.session.commit()
    return jsonify({"ok": True, "message": "Upload history updated"})


@dashboard_bp.route("/api/upload-logs/<int:log_id>/file", methods=["DELETE"])
@role_required("Admin", "Manager")
def delete_upload_file(log_id):
    log = db.session.get(UploadLog, log_id)
    if not log:
        return jsonify({"ok": False, "message": "Upload log was not found"}), 404

    removed = _delete_stored_upload_file(log)
    db.session.commit()
    message = "Excel file deleted from server" if removed else "Excel file was already missing"
    return jsonify({"ok": True, "message": message})


@dashboard_bp.route("/api/upload-logs/<int:log_id>", methods=["DELETE"])
@role_required("Admin", "Manager")
def delete_upload_log(log_id):
    log = db.session.get(UploadLog, log_id)
    if not log:
        return jsonify({"ok": False, "message": "Upload log was not found"}), 404

    _delete_stored_upload_file(log)
    deleted_facts = FactETD.query.filter(FactETD.UploadLogID == log.id).delete(synchronize_session=False)
    db.session.delete(log)
    db.session.commit()
    return jsonify({"ok": True, "message": f"Deleted upload history and {deleted_facts} imported rows"})


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
        upload_log_id = request.args.get("upload_log_id", type=int)
        if month:
            query = query.filter(FactETD.Month == month)
        if customer_id:
            query = query.filter(FactETD.CustomerID == customer_id)
        if market_id:
            query = query.filter(FactETD.MarketID == market_id)
        if upload_log_id:
            query = query.filter(FactETD.UploadLogID == upload_log_id)
        if search:
            query = query.filter(FactETD.PartNo.ilike(f"%{search}%"))
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
            "pk": _primary_key_column(model).name,
            "rows": [_serialize_model(row, columns) for row in pagination.items],
            "page": pagination.page,
            "pages": pagination.pages,
            "total": pagination.total,
        }
    )


@dashboard_bp.route("/api/admin/table-row", methods=["POST"])
@role_required("Admin")
def api_admin_create_row():
    payload = request.get_json(silent=True) or {}
    table = payload.get("table")
    model = TABLE_REGISTRY.get(table)
    if not model or table in {"users", "DATA_CHANGE_LOGS"}:
        return jsonify({"ok": False, "message": "This table cannot be created here"}), 400

    values = payload.get("values") or {}
    row = model()
    if isinstance(row, FactETD):
        row.created_by = current_user.username
        row.updated_by = current_user.username
        row.created_at = datetime.utcnow()
        row.updated_at = datetime.utcnow()
    _apply_payload_to_model(row, model, values)
    db.session.add(row)
    db.session.flush()
    row_id = getattr(row, _primary_key_column(model).name)
    _record_data_change(table, row_id, "create", str(values))
    db.session.commit()
    return jsonify({"ok": True, "message": "Row created"})


@dashboard_bp.route("/api/admin/table-row/<int:row_id>", methods=["PUT"])
@role_required("Admin")
def api_admin_update_row(row_id):
    payload = request.get_json(silent=True) or {}
    table = payload.get("table")
    model = TABLE_REGISTRY.get(table)
    if not model or table in {"users", "DATA_CHANGE_LOGS"}:
        return jsonify({"ok": False, "message": "This table cannot be edited here"}), 400
    row = db.session.get(model, row_id)
    if not row:
        return jsonify({"ok": False, "message": "Row not found"}), 404
    changed = _apply_payload_to_model(row, model, payload.get("values") or {})
    if changed:
        _record_data_change(table, row_id, "update", str(changed))
    db.session.commit()
    return jsonify({"ok": True, "message": "Row updated"})


@dashboard_bp.route("/api/admin/table-row/<int:row_id>", methods=["DELETE"])
@role_required("Admin")
def api_admin_delete_row(row_id):
    table = request.args.get("table")
    model = TABLE_REGISTRY.get(table)
    if not model or table in {"users", "DATA_CHANGE_LOGS"}:
        return jsonify({"ok": False, "message": "This table cannot be deleted here"}), 400
    row = db.session.get(model, row_id)
    if not row:
        return jsonify({"ok": False, "message": "Row not found"}), 404
    _record_data_change(table, row_id, "delete", str(_serialize_model(row, _model_columns(model))))
    db.session.delete(row)
    db.session.commit()
    return jsonify({"ok": True, "message": "Row deleted"})


@dashboard_bp.route("/api/data/options")
@role_required("Admin", "Manager", "Staff")
def api_data_options():
    months = _data_months()
    years = sorted({label for label in (_fy_label_for_month(month) for month in months) if label}, reverse=True)
    return jsonify(
        {
            "uploads": [{"id": row.id, "text": _upload_label(row)} for row in _successful_upload_options()],
            "file_categories": [{"id": key, "text": value} for key, value in FILE_CATEGORIES.items()],
            "months": months,
            "years": years,
            "customers": [{"id": row.CustomerID, "text": row.Customer} for row in DimCustomer.query.order_by(DimCustomer.Customer).all()],
            "types": [{"id": row.TypeID, "text": row.Type} for row in DimType.query.order_by(DimType.Type).all()],
            "type2s": [{"id": row.Type2ID, "text": row.Type2} for row in DimType2.query.order_by(DimType2.Type2).all()],
            "lasers": [{"id": row.LaserID, "text": row.Laser} for row in DimLaser.query.order_by(DimLaser.Laser).all()],
            "country_of_makers": [{"id": row.CountryOfMakerID, "text": row.CountryOfMaker} for row in DimCountryOfMaker.query.order_by(DimCountryOfMaker.CountryOfMaker).all()],
            "car_makers": [{"id": row.CarMakerID, "text": row.CarMaker} for row in DimCarMaker.query.order_by(DimCarMaker.CarMaker).all()],
            "countries": [{"id": row.CountryID, "text": row.Country} for row in DimCountry.query.order_by(DimCountry.Country).all()],
            "markets": [{"id": row.MarketID, "text": row.Market} for row in DimMarket.query.order_by(DimMarket.Market).all()],
        }
    )


@dashboard_bp.route("/api/data/facts")
@role_required("Admin", "Manager", "Staff")
def api_data_facts():
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(max(request.args.get("per_page", 50, type=int), 10), 200)
    query = _base_query()
    upload_log_id = request.args.get("upload_log_id", type=int)
    search = request.args.get("search", "").strip()
    filters = {
        "CustomerID": request.args.get("customer_id", type=int),
        "TypeID": request.args.get("type_id", type=int),
        "Type2ID": request.args.get("type2_id", type=int),
        "LaserID": request.args.get("laser_id", type=int),
        "CountryOfMakerID": request.args.get("country_maker_id", type=int),
        "CountryID": request.args.get("country_id", type=int),
        "MarketID": request.args.get("market_id", type=int),
        "CarMakerID": request.args.get("car_maker_id", type=int),
    }
    month = request.args.get("month", "").strip()
    if upload_log_id:
        query = query.filter(FactETD.UploadLogID == upload_log_id)
    for column, value in filters.items():
        if value:
            query = query.filter(getattr(FactETD, column) == value)
    if month:
        query = query.filter(FactETD.Month == month)
    if search:
        query = query.filter(FactETD.PartNo.ilike(f"%{search}%"))
    pagination = query.order_by(FactETD.PartNo.asc(), FactETD.Month.asc()).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify(
        {
            "ok": True,
            "rows": [_fact_display_row(item) for item in pagination.items],
            "page": pagination.page,
            "pages": pagination.pages,
            "total": pagination.total,
        }
    )


def _apply_data_filters(query):
    upload_log_id = request.args.get("upload_log_id", type=int)
    file_category = request.args.get("file_category", "").strip()
    search = request.args.get("search", "").strip()
    filters = {
        "CustomerID": request.args.get("customer_id", type=int),
        "TypeID": request.args.get("type_id", type=int),
        "Type2ID": request.args.get("type2_id", type=int),
        "LaserID": request.args.get("laser_id", type=int),
        "CountryOfMakerID": request.args.get("country_maker_id", type=int),
        "CountryID": request.args.get("country_id", type=int),
        "MarketID": request.args.get("market_id", type=int),
        "CarMakerID": request.args.get("car_maker_id", type=int),
    }
    if upload_log_id:
        query = query.filter(FactETD.UploadLogID == upload_log_id)
    if file_category:
        query = query.filter(UploadLog.file_category == file_category)
    for column, value in filters.items():
        if value:
            query = query.filter(getattr(FactETD, column) == value)
    if search:
        query = query.filter(FactETD.PartNo.ilike(f"%{search}%"))
    return query


def _fact_identity(item):
    return "|".join(
        str(value)
        for value in [
            item.UploadLogID,
            item.PartNo,
            item.CustomerID,
            item.TypeID,
            item.Type2ID,
            item.LaserID,
            item.CountryOfMakerID,
            item.CarMakerID,
            item.CountryID,
            item.MarketID,
        ]
    )


@dashboard_bp.route("/api/data/matrix")
@role_required("Admin", "Manager", "Staff")
def api_data_matrix():
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(max(request.args.get("per_page", 30, type=int), 10), 100)
    month_from = request.args.get("month_from")
    month_to = request.args.get("month_to")
    fiscal_year = request.args.get("fiscal_year")
    selected_months = _data_allowed_months(month_from, month_to, fiscal_year)
    query = _apply_data_filters(_base_query())
    if selected_months:
        query = query.filter(FactETD.Month.in_(selected_months))

    items = query.order_by(FactETD.PartNo.asc(), FactETD.Month.asc()).all()
    grouped = {}
    for item in items:
        key = _fact_identity(item)
        if key not in grouped:
            grouped[key] = {
                "key": key,
                "UploadLogID": item.UploadLogID,
                "File": _upload_label(item.upload_log),
                "PartNo": item.PartNo,
                "CustomerID": item.CustomerID,
                "Customer": item.customer.Customer,
                "TypeID": item.TypeID,
                "Type": item.type.Type,
                "Type2ID": item.Type2ID,
                "Type2": item.type2.Type2,
                "LaserID": item.LaserID,
                "Laser": item.laser.Laser,
                "CountryOfMakerID": item.CountryOfMakerID,
                "CountryOfMaker": item.country_of_maker.CountryOfMaker,
                "CarMakerID": item.CarMakerID,
                "CarMaker": item.car_maker.CarMaker,
                "CountryID": item.CountryID,
                "Country": item.country.Country,
                "MarketID": item.MarketID,
                "Market": item.market.Market,
                "values": {},
            }
        grouped[key]["values"][item.Month] = {
            "id": item.ID,
            "value": item.Value,
            "updated_by": item.updated_by,
            "updated_at": _serialize_value(item.updated_at),
        }

    rows = list(grouped.values())
    total = len(rows)
    start = (page - 1) * per_page
    end = start + per_page
    pages = (total + per_page - 1) // per_page
    return jsonify(
        {
            "ok": True,
            "months": selected_months,
            "rows": rows[start:end],
            "page": page,
            "pages": pages,
            "total": total,
        }
    )


@dashboard_bp.route("/api/data/matrix-cell", methods=["POST"])
@role_required("Admin", "Manager", "Staff")
def api_data_matrix_cell():
    payload = request.get_json(silent=True) or {}
    try:
        value = float(payload.get("value") or 0)
        month = str(payload.get("month") or "").strip()
        if not month:
            raise ValueError("Month is required")
        values = {
            "UploadLogID": int(payload["UploadLogID"]),
            "PartNo": str(payload["PartNo"]).strip(),
            "CustomerID": int(payload["CustomerID"]),
            "TypeID": int(payload["TypeID"]),
            "Type2ID": int(payload["Type2ID"]),
            "LaserID": int(payload["LaserID"]),
            "CountryOfMakerID": int(payload["CountryOfMakerID"]),
            "CarMakerID": int(payload["CarMakerID"]),
            "CountryID": int(payload["CountryID"]),
            "MarketID": int(payload["MarketID"]),
            "Month": month,
            "Value": value,
        }
    except (KeyError, ValueError) as exc:
        return jsonify({"ok": False, "message": f"Invalid cell payload: {exc}"}), 400

    row = FactETD.query.filter_by(PartNo=values["PartNo"], Month=month, UploadLogID=values["UploadLogID"]).first()
    now = datetime.utcnow()
    if row:
        old = row.Value
        for key, item in values.items():
            setattr(row, key, item)
        row.updated_by = current_user.username
        row.updated_at = now
        _record_data_change("FACT_ETD", row.ID, "update", str({"Month": month, "old": old, "new": value}))
    else:
        row = FactETD(**values, created_by=current_user.username, updated_by=current_user.username, created_at=now, updated_at=now)
        db.session.add(row)
        db.session.flush()
        _record_data_change("FACT_ETD", row.ID, "create", str(values))
    db.session.commit()
    return jsonify({"ok": True, "message": "Saved", "id": row.ID})


@dashboard_bp.route("/api/data/check-partno")
@role_required("Admin", "Manager", "Staff")
def api_data_check_partno():
    part_no = request.args.get("part_no", "").strip()
    upload_log_id = request.args.get("upload_log_id", type=int)
    if not part_no or not upload_log_id:
        return jsonify({"exists": False})
    existing = FactETD.query.filter_by(PartNo=part_no, UploadLogID=upload_log_id).first()
    return jsonify({"exists": bool(existing)})


@dashboard_bp.route("/api/data/matrix-row", methods=["POST"])
@role_required("Admin", "Manager", "Staff")
def api_data_matrix_row():
    payload = request.get_json(silent=True) or {}
    try:
        month = str(payload.get("Month") or "").strip()
        if not month:
            raise ValueError("Month is required")
        values = {
            "UploadLogID": int(payload["UploadLogID"]),
            "PartNo": str(payload["PartNo"]).strip(),
            "CustomerID": int(payload["CustomerID"]),
            "TypeID": int(payload["TypeID"]),
            "Type2ID": int(payload["Type2ID"]),
            "LaserID": int(payload["LaserID"]),
            "CountryOfMakerID": int(payload["CountryOfMakerID"]),
            "CarMakerID": int(payload["CarMakerID"]),
            "CountryID": int(payload["CountryID"]),
            "MarketID": int(payload["MarketID"]),
            "Month": month,
            "Value": float(payload.get("Value") or 0),
        }
    except (KeyError, ValueError) as exc:
        return jsonify({"ok": False, "message": f"Invalid row payload: {exc}"}), 400

    if not values["PartNo"]:
        return jsonify({"ok": False, "message": "PartNo is required"}), 400

    # Check if this exact PartNo+Month+Upload combo already exists (DB unique constraint)
    existing_exact = FactETD.query.filter_by(PartNo=values["PartNo"], Month=values["Month"], UploadLogID=values["UploadLogID"]).first()
    if existing_exact:
        return jsonify({"ok": False, "message": "This PartNo/month already exists in the selected file"}), 400

    # Check if PartNo exists at all in this upload (warn but allow if user confirmed)
    force = payload.get("force", False)
    if not force:
        existing_partno = FactETD.query.filter_by(PartNo=values["PartNo"], UploadLogID=values["UploadLogID"]).first()
        if existing_partno:
            return jsonify({"ok": False, "duplicate_partno": True, "message": f"PartNo '{values['PartNo']}' already exists in this file. Do you want to continue adding this row?"}), 409

    now = datetime.utcnow()
    row = FactETD(**values, created_by=current_user.username, updated_by=current_user.username, created_at=now, updated_at=now)
    db.session.add(row)
    db.session.flush()
    _record_data_change("FACT_ETD", row.ID, "create", str(values))
    db.session.commit()
    return jsonify({"ok": True, "message": "Row created successfully", "id": row.ID})


def _fact_values_from_payload(payload):
    required = ["PartNo", "CustomerID", "TypeID", "Type2ID", "LaserID", "CountryOfMakerID", "CarMakerID", "CountryID", "MarketID", "Month", "Value", "UploadLogID"]
    missing = [key for key in required if payload.get(key) in {None, ""}]
    if missing:
        raise ValueError("Missing required fields: " + ", ".join(missing))
    return {
        "PartNo": str(payload["PartNo"]).strip(),
        "CustomerID": int(payload["CustomerID"]),
        "TypeID": int(payload["TypeID"]),
        "Type2ID": int(payload["Type2ID"]),
        "LaserID": int(payload["LaserID"]),
        "CountryOfMakerID": int(payload["CountryOfMakerID"]),
        "CarMakerID": int(payload["CarMakerID"]),
        "CountryID": int(payload["CountryID"]),
        "MarketID": int(payload["MarketID"]),
        "Month": str(payload["Month"]).strip(),
        "Value": float(payload["Value"]),
        "UploadLogID": int(payload["UploadLogID"]),
    }


@dashboard_bp.route("/api/data/facts", methods=["POST"])
@role_required("Admin", "Manager", "Staff")
def api_data_create_fact():
    payload = request.get_json(silent=True) or {}
    try:
        values = _fact_values_from_payload(payload)
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    existing = FactETD.query.filter_by(PartNo=values["PartNo"], Month=values["Month"], UploadLogID=values["UploadLogID"]).first()
    if existing:
        return jsonify({"ok": False, "message": "PartNo/month already exists for this file"}), 400
    now = datetime.utcnow()
    row = FactETD(**values, created_by=current_user.username, updated_by=current_user.username, created_at=now, updated_at=now)
    db.session.add(row)
    db.session.flush()
    _record_data_change("FACT_ETD", row.ID, "create", str(values))
    db.session.commit()
    return jsonify({"ok": True, "message": "Row created"})


@dashboard_bp.route("/api/data/facts/<int:fact_id>", methods=["PUT"])
@role_required("Admin", "Manager", "Staff")
def api_data_update_fact(fact_id):
    row = db.session.get(FactETD, fact_id)
    if not row:
        return jsonify({"ok": False, "message": "Row not found"}), 404
    payload = request.get_json(silent=True) or {}
    try:
        values = _fact_values_from_payload(payload)
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    changed = {}
    for key, value in values.items():
        if getattr(row, key) != value:
            changed[key] = {"old": _serialize_value(getattr(row, key)), "new": _serialize_value(value)}
            setattr(row, key, value)
    row.updated_by = current_user.username
    row.updated_at = datetime.utcnow()
    if changed:
        _record_data_change("FACT_ETD", row.ID, "update", str(changed))
    db.session.commit()
    return jsonify({"ok": True, "message": "Row updated"})


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
