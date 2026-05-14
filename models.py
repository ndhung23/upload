from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint, inspect, text
from werkzeug.security import generate_password_hash


db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    password_plain = db.Column(db.String(255), nullable=False, default="")
    full_name = db.Column(db.String(160), nullable=False, default="")
    employee_code = db.Column(db.String(50), nullable=False, default="", index=True)
    role = db.Column(db.String(20), nullable=False, default="Staff")
    manager_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    manager = db.relationship("User", remote_side=[id], backref="staff_members")


class DimCustomer(db.Model):
    __tablename__ = "DIM_Customer"

    CustomerID = db.Column(db.Integer, primary_key=True)
    Customer = db.Column(db.String(255), unique=True, nullable=False, index=True)


class DimType(db.Model):
    __tablename__ = "DIM_Type"

    TypeID = db.Column(db.Integer, primary_key=True)
    Type = db.Column(db.String(255), unique=True, nullable=False, index=True)


class DimLaser(db.Model):
    __tablename__ = "DIM_Laser"

    LaserID = db.Column(db.Integer, primary_key=True)
    Laser = db.Column(db.String(255), unique=True, nullable=False, index=True)


class DimCountryOfMaker(db.Model):
    __tablename__ = "DIM_CountryOfMaker"

    CountryOfMakerID = db.Column(db.Integer, primary_key=True)
    CountryOfMaker = db.Column(db.String(255), unique=True, nullable=False, index=True)


class DimCarMaker(db.Model):
    __tablename__ = "DIM_CarMaker"

    CarMakerID = db.Column(db.Integer, primary_key=True)
    CarMaker = db.Column(db.String(255), unique=True, nullable=False, index=True)


class DimCountry(db.Model):
    __tablename__ = "DIM_Country"

    CountryID = db.Column(db.Integer, primary_key=True)
    Country = db.Column(db.String(255), unique=True, nullable=False, index=True)


class DimMarket(db.Model):
    __tablename__ = "DIM_Market"

    MarketID = db.Column(db.Integer, primary_key=True)
    Market = db.Column(db.String(255), unique=True, nullable=False, index=True)


class DimType2(db.Model):
    __tablename__ = "DIM_Type2"

    Type2ID = db.Column(db.Integer, primary_key=True)
    Type2 = db.Column(db.String(255), unique=True, nullable=False, index=True)


class FactETD(db.Model):
    __tablename__ = "FACT_ETD"
    __table_args__ = (
        UniqueConstraint("PartNo", "Month", "UploadLogID", name="uq_fact_part_month_upload"),
    )

    ID = db.Column(db.Integer, primary_key=True)
    PartNo = db.Column(db.String(255), nullable=False, index=True)
    CustomerID = db.Column(db.Integer, db.ForeignKey("DIM_Customer.CustomerID"), nullable=False)
    TypeID = db.Column(db.Integer, db.ForeignKey("DIM_Type.TypeID"), nullable=False)
    LaserID = db.Column(db.Integer, db.ForeignKey("DIM_Laser.LaserID"), nullable=False)
    CountryOfMakerID = db.Column(
        db.Integer,
        db.ForeignKey("DIM_CountryOfMaker.CountryOfMakerID"),
        nullable=False,
    )
    CarMakerID = db.Column(db.Integer, db.ForeignKey("DIM_CarMaker.CarMakerID"), nullable=False)
    CountryID = db.Column(db.Integer, db.ForeignKey("DIM_Country.CountryID"), nullable=False)
    MarketID = db.Column(db.Integer, db.ForeignKey("DIM_Market.MarketID"), nullable=False)
    Type2ID = db.Column(db.Integer, db.ForeignKey("DIM_Type2.Type2ID"), nullable=False)
    Month = db.Column(db.String(20), nullable=False, index=True)
    Value = db.Column(db.Float, nullable=False, default=0)
    UploadLogID = db.Column(db.Integer, db.ForeignKey("UPLOAD_LOGS.id"), nullable=True, index=True)

    customer = db.relationship("DimCustomer")
    type = db.relationship("DimType")
    laser = db.relationship("DimLaser")
    country_of_maker = db.relationship("DimCountryOfMaker")
    car_maker = db.relationship("DimCarMaker")
    country = db.relationship("DimCountry")
    market = db.relationship("DimMarket")
    type2 = db.relationship("DimType2")
    upload_log = db.relationship("UploadLog")


class UploadLog(db.Model):
    __tablename__ = "UPLOAD_LOGS"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False, default="")
    uploaded_by = db.Column(db.String(80), nullable=False, index=True)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    total_rows = db.Column(db.Integer, nullable=False, default=0)
    inserted_rows = db.Column(db.Integer, nullable=False, default=0)
    updated_rows = db.Column(db.Integer, nullable=False, default=0)
    skipped_rows = db.Column(db.Integer, nullable=False, default=0)
    invalid_rows = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="success")
    message = db.Column(db.Text, nullable=False, default="")


def ensure_schema():
    inspector = inspect(db.engine)
    if "users" in inspector.get_table_names():
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if "is_active_flag" in user_columns:
            created_expr = "COALESCE(created_at, CURRENT_TIMESTAMP)" if "created_at" in user_columns else "CURRENT_TIMESTAMP"
            full_name_expr = "COALESCE(full_name, '')" if "full_name" in user_columns else "''"
            active_expr = "COALESCE(is_active, is_active_flag, 1)" if "is_active" in user_columns else "COALESCE(is_active_flag, 1)"
            with db.engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        CREATE TABLE users_migrated (
                            id INTEGER NOT NULL PRIMARY KEY,
                            username VARCHAR(80) NOT NULL UNIQUE,
                            password_hash VARCHAR(255) NOT NULL,
                            password_plain VARCHAR(255) DEFAULT '' NOT NULL,
                            full_name VARCHAR(160) DEFAULT '' NOT NULL,
                            employee_code VARCHAR(50) DEFAULT '' NOT NULL,
                            role VARCHAR(20) DEFAULT 'Staff' NOT NULL,
                            manager_id INTEGER,
                            created_at DATETIME NOT NULL,
                            is_active BOOLEAN DEFAULT 1 NOT NULL,
                            FOREIGN KEY(manager_id) REFERENCES users (id)
                        )
                        """
                    )
                )
                conn.execute(
                    text(
                        f"""
                        INSERT OR IGNORE INTO users_migrated
                        (id, username, password_hash, password_plain, full_name, employee_code, role, manager_id, created_at, is_active)
                        SELECT id, username, password_hash, '', {full_name_expr}, '', role, NULL, {created_expr}, {active_expr}
                        FROM users
                        """
                    )
                )
                conn.execute(text("DROP TABLE users"))
                conn.execute(text("ALTER TABLE users_migrated RENAME TO users"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_username ON users (username)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_employee_code ON users (employee_code)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_manager_id ON users (manager_id)"))
            return

        with db.engine.begin() as conn:
            if "full_name" not in user_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN full_name VARCHAR(160) DEFAULT '' NOT NULL"))
            if "password_plain" not in user_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN password_plain VARCHAR(255) DEFAULT '' NOT NULL"))
            if "employee_code" not in user_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN employee_code VARCHAR(50) DEFAULT '' NOT NULL"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_employee_code ON users (employee_code)"))
            if "manager_id" not in user_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN manager_id INTEGER"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_manager_id ON users (manager_id)"))
            if "created_at" not in user_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN created_at DATETIME"))
                conn.execute(text("UPDATE users SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
            if "is_active" not in user_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1 NOT NULL"))
                if "is_active_flag" in user_columns:
                    conn.execute(text("UPDATE users SET is_active = COALESCE(is_active_flag, 1)"))

    if "UPLOAD_LOGS" in inspector.get_table_names():
        log_columns = {column["name"] for column in inspector.get_columns("UPLOAD_LOGS")}
        with db.engine.begin() as conn:
            if "stored_filename" not in log_columns:
                conn.execute(text("ALTER TABLE UPLOAD_LOGS ADD COLUMN stored_filename VARCHAR(255) DEFAULT '' NOT NULL"))
            if "invalid_rows" not in log_columns:
                conn.execute(text("ALTER TABLE UPLOAD_LOGS ADD COLUMN invalid_rows INTEGER DEFAULT 0 NOT NULL"))
            if "message" not in log_columns:
                conn.execute(text("ALTER TABLE UPLOAD_LOGS ADD COLUMN message TEXT DEFAULT '' NOT NULL"))

    if "FACT_ETD" in inspector.get_table_names():
        fact_columns = {column["name"] for column in inspector.get_columns("FACT_ETD")}
        fact_sql = db.session.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='FACT_ETD'")
        ).scalar() or ""
        needs_upload_column = "UploadLogID" not in fact_columns
        needs_unique_migration = "uq_fact_part_month_upload" not in fact_sql
        if needs_upload_column or needs_unique_migration:
            with db.engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        CREATE TABLE FACT_ETD_migrated (
                            "ID" INTEGER NOT NULL PRIMARY KEY,
                            "PartNo" VARCHAR(255) NOT NULL,
                            "CustomerID" INTEGER NOT NULL,
                            "TypeID" INTEGER NOT NULL,
                            "LaserID" INTEGER NOT NULL,
                            "CountryOfMakerID" INTEGER NOT NULL,
                            "CarMakerID" INTEGER NOT NULL,
                            "CountryID" INTEGER NOT NULL,
                            "MarketID" INTEGER NOT NULL,
                            "Type2ID" INTEGER NOT NULL,
                            "Month" VARCHAR(20) NOT NULL,
                            "Value" FLOAT NOT NULL,
                            "UploadLogID" INTEGER,
                            CONSTRAINT uq_fact_part_month_upload UNIQUE ("PartNo", "Month", "UploadLogID"),
                            FOREIGN KEY("CustomerID") REFERENCES "DIM_Customer" ("CustomerID"),
                            FOREIGN KEY("TypeID") REFERENCES "DIM_Type" ("TypeID"),
                            FOREIGN KEY("LaserID") REFERENCES "DIM_Laser" ("LaserID"),
                            FOREIGN KEY("CountryOfMakerID") REFERENCES "DIM_CountryOfMaker" ("CountryOfMakerID"),
                            FOREIGN KEY("CarMakerID") REFERENCES "DIM_CarMaker" ("CarMakerID"),
                            FOREIGN KEY("CountryID") REFERENCES "DIM_Country" ("CountryID"),
                            FOREIGN KEY("MarketID") REFERENCES "DIM_Market" ("MarketID"),
                            FOREIGN KEY("Type2ID") REFERENCES "DIM_Type2" ("Type2ID"),
                            FOREIGN KEY("UploadLogID") REFERENCES "UPLOAD_LOGS" (id)
                        )
                        """
                    )
                )
                upload_expr = '"UploadLogID"' if "UploadLogID" in fact_columns else "NULL"
                conn.execute(
                    text(
                        f"""
                        INSERT OR IGNORE INTO FACT_ETD_migrated
                        ("ID", "PartNo", "CustomerID", "TypeID", "LaserID", "CountryOfMakerID",
                         "CarMakerID", "CountryID", "MarketID", "Type2ID", "Month", "Value", "UploadLogID")
                        SELECT "ID", "PartNo", "CustomerID", "TypeID", "LaserID", "CountryOfMakerID",
                               "CarMakerID", "CountryID", "MarketID", "Type2ID", "Month", "Value", {upload_expr}
                        FROM FACT_ETD
                        """
                    )
                )
                conn.execute(text("DROP TABLE FACT_ETD"))
                conn.execute(text("ALTER TABLE FACT_ETD_migrated RENAME TO FACT_ETD"))
                conn.execute(text('CREATE INDEX IF NOT EXISTS ix_FACT_ETD_PartNo ON FACT_ETD ("PartNo")'))
                conn.execute(text('CREATE INDEX IF NOT EXISTS ix_FACT_ETD_Month ON FACT_ETD ("Month")'))
                conn.execute(text('CREATE INDEX IF NOT EXISTS ix_FACT_ETD_UploadLogID ON FACT_ETD ("UploadLogID")'))


def seed_admin():
    seed_users = [
        ("admin", "admin123", "System Admin", "Admin", "ADMIN", None),
        ("manager", "manager123", "ETD Manager", "Manager", "MANAGER", None),
        ("staff", "staff123", "Dashboard Staff", "Staff", "STAFF", None),
        ("90122", "123", "Nguyễn Duy Hưng", "Staff", "90122", 1),
    ]

    for username, password, full_name, role, employee_code, manager_id in seed_users:
        user = User.query.filter_by(username=username).first()
        if user:
            user.full_name = user.full_name or full_name
            user.employee_code = user.employee_code or employee_code
            user.role = user.role or role
            if username == "90122":
                user.manager_id = manager_id
            user.is_active = True
            user.password_plain = user.password_plain or password
            continue
        db.session.add(
            User(
                username=username,
                password_hash=generate_password_hash(password),
                password_plain=password,
                full_name=full_name,
                employee_code=employee_code,
                role=role,
                manager_id=manager_id,
                is_active=True,
            )
        )
    db.session.commit()
