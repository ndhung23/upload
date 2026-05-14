import os
import re
from dataclasses import dataclass

import pandas as pd
from sqlalchemy.exc import IntegrityError

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
    db,
)


MONTH_REGEX = re.compile(r"^\d{2}-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$")
MONTH_NAME_REGEX = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$")
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

DIM_MAP = {
    "Customer": (DimCustomer, "CustomerID", "Customer"),
    "Type": (DimType, "TypeID", "Type"),
    "Laser": (DimLaser, "LaserID", "Laser"),
    "Country of maker": (DimCountryOfMaker, "CountryOfMakerID", "CountryOfMaker"),
    "Car maker": (DimCarMaker, "CarMakerID", "CarMaker"),
    "Country": (DimCountry, "CountryID", "Country"),
    "Market": (DimMarket, "MarketID", "Market"),
    "Type2": (DimType2, "Type2ID", "Type2"),
}

REQUIRED_COLUMNS = [
    "Customer",
    "Type",
    "Part No.",
    "Laser",
    "Country of maker",
    "Car maker",
    "Market",
]

COLUMN_ALIASES = {
    "customer": "Customer",
    "type": "Type",
    "part no.": "Part No.",
    "part no": "Part No.",
    "partno": "Part No.",
    "laser": "Laser",
    "country of maker": "Country of maker",
    "car maker": "Car maker",
    "column1": "Country",
    "country": "Country",
    "market": "Market",
    "market (easy)": "Market",
    "type2": "Type2",
}


class ETLError(Exception):
    pass


@dataclass
class ETLResult:
    total_rows: int
    inserted: int
    updated: int
    skipped: int
    invalid_rows: int
    dim_inserted: int
    rows_after_cleaning: int
    header_row: int
    table_rows: int


def _normalize_header(value):
    return re.sub(r"\s+", " ", str(value).strip()).lower()


def _canonical_column_name(value):
    text = str(value).strip()
    if MONTH_REGEX.match(text):
        return text
    if MONTH_NAME_REGEX.match(text):
        return text
    parsed_date = pd.to_datetime(value, errors="coerce")
    if not pd.isna(parsed_date) and getattr(parsed_date, "year", 1900) >= 2000:
        return f"{parsed_date.year % 100:02d}-{parsed_date.strftime('%b')}"
    return COLUMN_ALIASES.get(_normalize_header(value), text)


def _normalize_columns(columns):
    mapping = {}
    for original in columns:
        canonical = _canonical_column_name(original)
        if canonical not in mapping:
            mapping[canonical] = original
    return mapping


def _clean_text(value):
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text in {"", "-"}:
        return ""
    return text


def _clean_value(series):
    cleaned = (
        series.astype(str)
        .str.strip()
        .str.replace(",", "", regex=False)
        .str.replace("-", "", regex=False)
    )
    cleaned = cleaned.replace({"": None, "nan": None, "None": None})
    return pd.to_numeric(cleaned, errors="coerce")


GARBAGE_REGEX = re.compile(
    r"(#REF!|TOTAL|^FC$|^RAP$|VS\s+AP|VS\s+RAP|LAST\s+MONTH|LAST\s+YEAR|AMOUNT)",
    re.IGNORECASE,
)
PART_NO_REGEX = re.compile(r"^[A-Z0-9\-]+$")


def _row_values(row):
    return [_clean_text(value) for value in row.tolist()]


def _row_contains_garbage(row):
    text = " ".join(_row_values(row))
    return bool(GARBAGE_REGEX.search(text))


def _valid_part_no(value):
    part_no = _clean_text(value)
    if not part_no:
        return False
    if re.search(r"(TOTAL|FC|RAP)", part_no, re.IGNORECASE):
        return False
    return bool(PART_NO_REGEX.fullmatch(part_no))


def _has_month_data(row, month_columns):
    if not month_columns:
        return False
    values = _clean_value(row[month_columns])
    return bool(values.notna().any())


def _detect_header_row(raw_df):
    required = set(REQUIRED_COLUMNS)
    for idx, row in raw_df.iterrows():
        canonical_values = {_canonical_column_name(value) for value in row.tolist()}
        if required.issubset(canonical_values):
            return idx
    raise ETLError("Cannot detect table header row with required ETD columns")


def _make_unique_columns(columns):
    seen = {}
    result = []
    for column in columns:
        canonical = _canonical_column_name(column)
        if canonical in seen:
            seen[canonical] += 1
            canonical = f"{canonical}__{seen[canonical]}"
        else:
            seen[canonical] = 0
        result.append(canonical)
    return result


def _infer_fiscal_year(raw_df, file_path):
    text_parts = [os.path.basename(file_path)]
    for _, row in raw_df.head(5).iterrows():
        text_parts.extend(_row_values(row))
    text = " ".join(text_parts)
    match = re.search(r"FY\s*20?(\d{2})", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _month_with_fiscal_year(month_name, fiscal_year):
    if not fiscal_year:
        return month_name
    year = fiscal_year if MONTH_ORDER[month_name] >= 4 else fiscal_year + 1
    return f"{year % 100:02d}-{month_name}"


def _prepare_flexible_columns(df, fiscal_year):
    rename = {}
    for column in df.columns:
        base = str(column).split("__", 1)[0]
        if MONTH_NAME_REGEX.match(base):
            rename[column] = _month_with_fiscal_year(base, fiscal_year)
    if rename:
        df = df.rename(columns=rename)
        df.columns = _make_unique_columns(df.columns)

    if "Type__1" in df.columns:
        df["Type2"] = df["Type"]
        df["Type"] = df["Type__1"]
    elif "Type2" not in df.columns and "Type" in df.columns:
        df["Type2"] = df["Type"]

    if "Country" not in df.columns:
        df["Country"] = df["Market"] if "Market" in df.columns else ""

    return df


def _extract_main_table(raw_df, file_path):
    header_idx = _detect_header_row(raw_df)
    header = _make_unique_columns(raw_df.iloc[header_idx].tolist())
    df = raw_df.iloc[header_idx + 1 :].copy()
    df.columns = header
    df = df.dropna(how="all")
    df = _prepare_flexible_columns(df, _infer_fiscal_year(raw_df, file_path))

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ETLError("Missing required columns after header detection: " + ", ".join(missing))

    month_columns = [col for col in df.columns if MONTH_REGEX.match(str(col).strip())]
    if not month_columns:
        raise ETLError("No valid month columns found. Expected format like 24-Apr or 25-Jan")

    valid_indexes = []
    invalid_rows = 0
    consecutive_empty_customer = 0
    data_started = False

    for idx, row in df.iterrows():
        if row.isna().all():
            invalid_rows += 1
            if data_started:
                consecutive_empty_customer += 1
            continue

        customer = _clean_text(row.get("Customer"))
        part_no = _clean_text(row.get("Part No."))

        if not customer:
            consecutive_empty_customer += 1
        else:
            consecutive_empty_customer = 0

        if data_started and consecutive_empty_customer >= 2:
            break

        if data_started and not part_no:
            break

        if _row_contains_garbage(row):
            if data_started:
                break
            invalid_rows += 1
            continue

        if not _valid_part_no(part_no):
            invalid_rows += 1
            continue

        if not _has_month_data(row, month_columns):
            invalid_rows += 1
            continue

        data_started = True
        valid_indexes.append(idx)

    if not valid_indexes:
        raise ETLError("No valid main table rows detected after header row")

    main_df = df.loc[valid_indexes, list(DIM_MAP.keys()) + ["Part No."] + month_columns].copy()
    return main_df, month_columns, header_idx + 1, invalid_rows


def _get_or_create_dim(model, key_col, value_col, value, cache):
    cache_key = (model.__tablename__, value)
    if cache_key in cache:
        return cache[cache_key], False

    row = model.query.filter(getattr(model, value_col) == value).first()
    if row:
        dim_id = getattr(row, key_col)
        cache[cache_key] = dim_id
        return dim_id, False

    row = model(**{value_col: value})
    db.session.add(row)
    db.session.flush()
    dim_id = getattr(row, key_col)
    cache[cache_key] = dim_id
    return dim_id, True


def process_excel(file_path, upload_log_id=None):
    if not os.path.exists(file_path):
        raise ETLError("Uploaded file was not found")

    try:
        xl = pd.ExcelFile(file_path)
        sheet_name = "ETD detail" if "ETD detail" in xl.sheet_names else xl.sheet_names[0]
        raw_df = pd.read_excel(file_path, sheet_name=sheet_name, dtype=object, header=None)
    except Exception as exc:
        raise ETLError(f"Cannot read Excel file: {exc}") from exc

    if raw_df.empty:
        raise ETLError("Excel file has no data")

    df, month_columns, header_row, invalid_rows = _extract_main_table(raw_df, file_path)

    id_columns = list(DIM_MAP.keys()) + ["Part No."]
    long_df = pd.melt(
        df[id_columns + month_columns],
        id_vars=id_columns,
        value_vars=month_columns,
        var_name="Month",
        value_name="Value",
    )

    long_df["Part No."] = long_df["Part No."].apply(_clean_text)
    long_df["Month"] = long_df["Month"].astype(str).str.strip()
    long_df["Value"] = _clean_value(long_df["Value"])

    for dim_col in DIM_MAP:
        long_df[dim_col] = long_df[dim_col].apply(_clean_text)

    valid_fact_mask = (
        (long_df["Part No."] != "")
        & long_df["Value"].notna()
        & (long_df["Month"] != "")
    )
    dropped_after_melt = int((~valid_fact_mask).sum())

    long_df = long_df[valid_fact_mask].copy()
    invalid_rows += dropped_after_melt

    if long_df.empty:
        raise ETLError("No valid fact rows after cleaning empty, '-' and NaN values")

    inserted = 0
    updated = 0
    skipped = 0
    dim_inserted = 0
    dim_cache = {}

    try:
        for row in long_df.to_dict(orient="records"):
            dim_ids = {}
            for source_col, (model, key_col, value_col) in DIM_MAP.items():
                dim_value = row[source_col]
                dim_id, created = _get_or_create_dim(model, key_col, value_col, dim_value, dim_cache)
                dim_ids[key_col] = dim_id
                dim_inserted += int(created)

            existing = FactETD.query.filter_by(
                PartNo=row["Part No."],
                Month=row["Month"],
                UploadLogID=upload_log_id,
            ).first()

            payload = {
                "PartNo": row["Part No."],
                "CustomerID": dim_ids["CustomerID"],
                "TypeID": dim_ids["TypeID"],
                "LaserID": dim_ids["LaserID"],
                "CountryOfMakerID": dim_ids["CountryOfMakerID"],
                "CarMakerID": dim_ids["CarMakerID"],
                "CountryID": dim_ids["CountryID"],
                "MarketID": dim_ids["MarketID"],
                "Type2ID": dim_ids["Type2ID"],
                "Month": row["Month"],
                "Value": float(row["Value"]),
                "UploadLogID": upload_log_id,
            }

            if existing:
                changed = False
                for key, value in payload.items():
                    if getattr(existing, key) != value:
                        setattr(existing, key, value)
                        changed = True
                updated += int(changed)
                skipped += int(not changed)
            else:
                db.session.add(FactETD(**payload))
                inserted += 1

        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ETLError(f"Database constraint error: {exc}") from exc
    except Exception:
        db.session.rollback()
        raise

    return ETLResult(
        total_rows=len(df),
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        invalid_rows=invalid_rows,
        dim_inserted=dim_inserted,
        rows_after_cleaning=len(long_df),
        header_row=header_row,
        table_rows=len(df),
    )
