# ETD Dashboard - Technical Handoff Report

Tài liệu này mô tả chi tiết hệ thống ETD Dashboard hiện tại để developer hoặc AI khác có thể tiếp tục phát triển project mà không cần đọc lại toàn bộ lịch sử trao đổi.

## 1. Tổng Quan Hệ Thống

ETD Dashboard là web nội bộ dùng để upload file Excel production/report, xử lý ETL từ wide format sang long fact table, lưu vào SQLite, hiển thị dashboard BI, quản lý user theo role, export dữ liệu, xem lịch sử upload và tra cứu dữ liệu database qua Admin Data Explorer.

Stack đang dùng:

- Backend: Python, Flask, Flask-Login, Flask-SQLAlchemy, SQLAlchemy ORM.
- Database: SQLite file local.
- Data processing: Pandas, OpenPyXL.
- Frontend: Bootstrap 5, Plotly.js, DataTables.js, Fetch API.
- Auth: session login, password hash bằng Werkzeug.
- Security: role decorator, CSRF token basic, SQL console chỉ cho SELECT.

Default URL khi chạy local:

```text
http://127.0.0.1:5000
```

Default database:

```text
database/company_dashboard.db
```

Có thể override database bằng biến môi trường:

```powershell
$env:DATABASE_URL="sqlite:///D:/path/company_dashboard.db"
```

## 2. Tài Khoản Seed

Hệ thống tự seed user khi app khởi động qua `seed_admin()` trong `models.py`.

Seed hiện tại:

| Username | Password | Full Name | Role | Employee Code | Manager |
|---|---:|---|---|---|---|
| admin | admin123 | System Admin | Admin | ADMIN | none |
| manager | manager123 | ETD Manager | Manager | MANAGER | none |
| staff | staff123 | Dashboard Staff | Staff | STAFF | none |
| 90122 | 123 | Nguyễn Duy Hưng | Staff | 90122 | user id 1 |

Lưu ý: yêu cầu hiện tại gán user `90122` thuộc quản lý có `manager_id = 1`. Trong database hiện tại, id 1 thường là `admin` vì admin được seed trước. Nếu nghiệp vụ muốn thuộc user `manager`, cần đổi `manager_id` sang id của user `manager` hoặc viết logic lookup theo username thay vì id cứng.

## 3. Phân Quyền

Role:

- Admin:
  - Xem dashboard.
  - Upload Excel.
  - Export Excel.
  - Xem upload history.
  - CRUD users.
  - Gán staff thuộc manager/admin.
  - Truy cập Admin Data Explorer.
  - Chạy SQL Console SELECT-only.
- Manager:
  - Xem dashboard.
  - Upload Excel.
  - Export Excel.
  - Xem upload history.
  - Đổi mật khẩu của chính mình.
- Staff:
  - Chỉ xem dashboard.
  - Đổi mật khẩu của chính mình.

Role checking nằm trong decorator `role_required(*roles)` tại `auth.py`.

## 4. Cấu Trúc Project

```text
.
|-- app.py
|-- auth.py
|-- dashboard.py
|-- etl.py
|-- export_service.py
|-- models.py
|-- requirements.txt
|-- README.md
|-- PROJECT_HANDOFF.md
|-- database/
|   `-- company_dashboard.db        # runtime DB, ignored by git
|-- uploads/
|   `-- .gitkeep
|-- templates/
|   |-- _flash.html
|   |-- base.html
|   |-- change_password.html
|   |-- dashboard.html
|   |-- data_explorer.html
|   |-- error.html
|   |-- login.html
|   |-- upload.html
|   |-- upload_history.html
|   `-- users.html
`-- static/
    |-- css/
    |   `-- app.css
    `-- js/
        |-- app.js
        |-- dashboard.js
        |-- data_explorer.js
        |-- upload.js
        `-- upload_history.js
```

## 5. Chi Tiết Từng File Python

### 5.1 `app.py`

Vai trò:

- Entry point của Flask application.
- Tạo Flask app trong `create_app()`.
- Cấu hình database, upload folder, session lifetime, secret key.
- Khởi tạo SQLAlchemy `db`.
- Khởi tạo Flask-Login.
- Register blueprint:
  - `auth_bp` từ `auth.py`
  - `dashboard_bp` từ `dashboard.py`
- Tạo database tables bằng `db.create_all()`.
- Chạy migration nhẹ bằng `ensure_schema()`.
- Seed tài khoản bằng `seed_admin()`.
- Inject global template variables:
  - `csrf_token`
  - `current_user`
- Route `/` redirect:
  - đã login -> `/dashboard`
  - chưa login -> `/login`
- Error handlers:
  - 403 -> `error.html`
  - 404 -> `error.html`
  - 413 file too large -> `error.html`

Config quan trọng:

```python
SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///.../database/company_dashboard.db")
UPLOAD_FOLDER = ".../uploads"
MAX_CONTENT_LENGTH = 64 * 1024 * 1024
PERMANENT_SESSION_LIFETIME = 8 hours
```

Lưu ý phát triển:

- Vì `SECRET_KEY` sinh random nếu không set env, session có thể invalid sau restart. Production nên set `SECRET_KEY` cố định.
- SQLite path mặc định là local file, không phải TCP database.

### 5.2 `models.py`

Vai trò:

- Định nghĩa SQLAlchemy ORM models.
- Chứa schema migration nhẹ cho bảng cũ.
- Seed tài khoản mặc định.

Models:

#### `User`

Table: `users`

Columns:

- `id`: primary key.
- `username`: unique, index, dùng để login.
- `password_hash`: password đã hash.
- `full_name`: họ tên.
- `employee_code`: mã nhân viên dạng string.
- `role`: `Admin`, `Manager`, hoặc `Staff`.
- `manager_id`: foreign key trỏ về `users.id`, dùng quan hệ manager - staff.
- `created_at`: thời điểm tạo.
- `is_active`: bật/tắt account.

Relationship:

```python
manager = db.relationship("User", remote_side=[id], backref="staff_members")
```

Ý nghĩa:

- `user.manager` trả về manager của user.
- `manager.staff_members` trả về danh sách user thuộc manager đó.

#### Dimension Tables

Các DIM dùng surrogate key, text unique:

- `DimCustomer`: `DIM_Customer(CustomerID, Customer)`
- `DimType`: `DIM_Type(TypeID, Type)`
- `DimLaser`: `DIM_Laser(LaserID, Laser)`
- `DimCountryOfMaker`: `DIM_CountryOfMaker(CountryOfMakerID, CountryOfMaker)`
- `DimCarMaker`: `DIM_CarMaker(CarMakerID, CarMaker)`
- `DimCountry`: `DIM_Country(CountryID, Country)`
- `DimMarket`: `DIM_Market(MarketID, Market)`
- `DimType2`: `DIM_Type2(Type2ID, Type2)`

#### `FactETD`

Table: `FACT_ETD`

Columns:

- `ID`: primary key.
- `PartNo`: business key, không tạo DIM.
- `CustomerID`
- `TypeID`
- `LaserID`
- `CountryOfMakerID`
- `CarMakerID`
- `CountryID`
- `MarketID`
- `Type2ID`
- `Month`
- `Value`

Constraint:

```python
UniqueConstraint("PartNo", "Month", name="uq_fact_part_month")
```

Ý nghĩa:

- Một `PartNo` chỉ có một dòng cho mỗi `Month`.
- Upload lại file không tạo duplicate.
- Nếu value/dim mapping thay đổi thì update dòng cũ.
- Nếu không đổi thì skipped.

#### `UploadLog`

Table: `UPLOAD_LOGS`

Columns:

- `id`
- `filename`
- `uploaded_by`
- `uploaded_at`
- `total_rows`
- `inserted_rows`
- `updated_rows`
- `skipped_rows`
- `invalid_rows`
- `status`
- `message`

Mục đích:

- Ghi lịch sử upload thành công/thất bại.
- Hiển thị ở `/upload-history`.

#### `ensure_schema()`

Đây là migration nhẹ, dùng khi không có Alembic.

Nó xử lý:

- Bảng `users` cũ có `is_active_flag` thì migrate sang schema mới.
- Thêm cột thiếu:
  - `full_name`
  - `employee_code`
  - `manager_id`
  - `created_at`
  - `is_active`
- Tạo indexes:
  - `ix_users_username`
  - `ix_users_employee_code`
  - `ix_users_manager_id`
- Bảng `UPLOAD_LOGS` cũ thì thêm:
  - `invalid_rows`
  - `message`

Lưu ý:

- Đây không phải migration framework đầy đủ.
- Nếu schema phức tạp hơn trong tương lai, nên chuyển sang Flask-Migrate/Alembic.

#### `seed_admin()`

Seed các tài khoản mặc định. Tên hàm vẫn là `seed_admin()` nhưng hiện seed nhiều account, không chỉ admin.

### 5.3 `auth.py`

Vai trò:

- Authentication.
- User management.
- Role decorator.
- CSRF check basic.
- Change password.

Constants:

```python
ROLES = ("Admin", "Manager", "Staff")
```

Functions:

- `validate_csrf()`: lấy token từ form `_csrf_token` hoặc header `X-CSRFToken`.
- `csrf_protect()`: chặn POST/PUT/PATCH/DELETE nếu token sai.
- `role_required(*roles)`: decorator yêu cầu login và role phù hợp.

Routes:

#### `GET/POST /login`

- GET render `login.html`.
- POST kiểm tra username/password.
- Dùng `check_password_hash`.
- Nếu account inactive thì không login.

#### `POST /logout`

- Yêu cầu login.
- Logout current session.

#### `GET /users`

- Chỉ Admin.
- Render `users.html`.
- Load toàn bộ users.
- Load danh sách manager candidate:
  - role in `Admin`, `Manager`
  - `is_active = True`

#### `POST /users/create`

- Chỉ Admin.
- Tạo user mới.
- Nhận:
  - username
  - password
  - full_name
  - employee_code
  - role
  - manager_id
- Hash password trước khi lưu.

#### `POST /users/<user_id>/update`

- Chỉ Admin.
- Update:
  - role
  - full_name
  - employee_code
  - manager_id
  - is_active
  - password nếu nhập password mới
- Có guard không cho user tự gán manager là chính nó.

#### `GET/POST /change-password`

- Mọi user đã login.
- GET render `change_password.html`.
- POST yêu cầu:
  - current_password
  - new_password
  - confirm_password
- Validate current password đúng.
- New password tối thiểu 3 ký tự.
- Confirm phải khớp.
- Lưu password hash mới.

#### `POST /users/<user_id>/delete`

- Chỉ Admin.
- Không cho xóa chính mình.

### 5.4 `etl.py`

Vai trò:

- Xử lý file Excel upload bằng Pandas.
- Detect header row tự động.
- Detect vùng table chính.
- Loại bỏ dữ liệu rác phía dưới file.
- Chuyển wide format sang long format.
- Insert/update DIM và FACT.

Regex:

```python
MONTH_REGEX = r"^\d{2}-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$"
PART_NO_REGEX = r"^[A-Z0-9\-]+$"
```

Month hợp lệ:

- `24-Apr`
- `24-May`
- `25-Jan`

Garbage markers:

```text
#REF!
TOTAL
FC
RAP
VS AP
VS RAP
LAST MONTH
LAST YEAR
AMOUNT
```

Column aliases:

- `Customer` -> `Customer`
- `Type` -> `Type`
- `Part No.` / `Part No` / `PartNo` -> `Part No.`
- `Laser` -> `Laser`
- `Country of maker` -> `Country of maker`
- `Car maker` -> `Car maker`
- `Column1` -> `Country`
- `Market` / `Market (easy)` -> `Market`
- `Type2` -> `Type2`

Lưu ý quan trọng:

- File thực tế có cột `Column1`, hệ thống map cột này vào `DIM_Country`.
- Nếu sau này Excel đổi tên cột country khác, cần thêm alias vào `COLUMN_ALIASES`.

ETL flow trong `process_excel(file_path)`:

1. Kiểm tra file tồn tại.
2. Đọc Excel:

```python
pd.read_excel(file_path, dtype=object, header=None)
```

3. Detect header row bằng `_detect_header_row(raw_df)`:
   - Scan từng row.
   - Chuẩn hóa từng cell thành canonical column name.
   - Row nào chứa đủ required columns thì là header.

Required columns:

```text
Customer
Type
Part No.
Laser
Country of maker
Car maker
Market
Type2
```

4. `_extract_main_table(raw_df)`:
   - Dùng row header làm column names.
   - Bỏ toàn bộ row phía trên.
   - Tạo unique column names nếu trùng.
   - Nếu thiếu `Country` thì tạo empty, nhưng hiện `Column1` đã map thành `Country`.
   - Detect month columns bằng regex.
   - Scan từng dòng data:
     - bỏ row toàn null.
     - dừng khi Customer null liên tiếp nhiều dòng sau khi data đã bắt đầu.
     - dừng khi Part No null sau khi data đã bắt đầu.
     - dừng nếu gặp garbage marker sau khi table đã bắt đầu.
     - skip nếu Part No invalid.
     - skip nếu không có numeric month data.
   - Return main table sạch.

5. Melt wide -> long:

```python
pd.melt(
    df[id_columns + month_columns],
    id_vars=id_columns,
    value_vars=month_columns,
    var_name="Month",
    value_name="Value",
)
```

6. Clean:
   - `Part No.` strip string.
   - `Month` strip string.
   - `Value`:
     - remove comma.
     - remove `-`.
     - convert numeric.
     - non-numeric -> NaN -> drop.

7. Insert DIM:
   - `_get_or_create_dim()`
   - Nếu text tồn tại thì reuse ID.
   - Nếu chưa tồn tại thì insert.
   - Có cache trong từng upload để giảm query.

8. Build FACT payload.

9. Duplicate handling:
   - Query existing by `PartNo + Month`.
   - Nếu có existing:
     - compare toàn bộ payload.
     - khác thì update và `updated += 1`.
     - giống thì `skipped += 1`.
   - Nếu chưa có:
     - insert và `inserted += 1`.

10. Commit transaction.

ETL result:

```python
ETLResult(
    total_rows,
    inserted,
    updated,
    skipped,
    invalid_rows,
    dim_inserted,
    rows_after_cleaning,
    header_row,
    table_rows,
)
```

Known behavior:

- `invalid_rows` hiện cộng cả invalid source rows và fact cells bị drop sau melt. Vì mỗi source row có nhiều month columns, số invalid có thể lớn hơn số row Excel.
- Nếu muốn báo cáo validation theo source row riêng và fact cell riêng, nên tách thêm field:
  - `invalid_source_rows`
  - `invalid_fact_cells`

### 5.5 `dashboard.py`

Vai trò:

- Dashboard routes.
- Upload routes.
- Export route.
- Upload logs API.
- Admin Data Explorer.
- SQL Console SELECT-only.

Imports chính:

- Flask: `Blueprint`, `jsonify`, `request`, `send_file`, etc.
- Flask-Login: `current_user`, `login_required`.
- SQLAlchemy: `func`, `or_`, `text`.
- ETL: `process_excel`, `ETLError`.
- Export: `build_export_workbook`.
- Models: FACT, DIM, User, UploadLog.

Blueprint:

```python
dashboard_bp = Blueprint("dashboard", __name__)
```

Table registry cho Admin Explorer:

```python
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
```

SQL forbidden keywords:

```text
UPDATE, DELETE, DROP, INSERT, ALTER, CREATE, REPLACE, TRUNCATE, PRAGMA, ATTACH, DETACH
```

Helper functions:

- `_month_key(month)`: sort month dạng `24-Apr`.
- `_allowed_months(month_from=None, month_to=None)`: lấy danh sách month distinct và filter range.
- `_base_query()`: query FACT join DIM chính cho dashboard.
- `_apply_filters(query)`: apply filter customer/type/country/car maker/market/month range.
- `_serialize_value(value)`: datetime -> string.
- `_model_columns(model)`: lấy columns của model.
- `_serialize_model(row, columns)`: convert row ORM thành dict.
- `_create_upload_log(...)`: ghi `UPLOAD_LOGS`.
- `_validate_select_sql(sql)`: chỉ cho SELECT, chặn multi statement và keyword nguy hiểm.

Routes:

#### `GET /dashboard`

- Yêu cầu login.
- Render `dashboard.html`.

#### `GET /upload`

- Admin/Manager.
- Render `upload.html`.

#### `GET /upload-history`

- Admin/Manager.
- Render `upload_history.html`.

#### `GET /admin/data-explorer`

- Chỉ Admin.
- Render `data_explorer.html`.
- Truyền list table từ `TABLE_REGISTRY`.

#### `GET /api/filter`

- Yêu cầu login.
- Trả filter dropdown data:
  - customers
  - types
  - countries
  - car_makers
  - markets
  - months

#### `GET /api/dashboard`

- Yêu cầu login.
- Query dashboard theo filter.
- Trả JSON:
  - stats:
    - total_value
    - total_part_no
    - total_customer
    - total_market
    - top_customer
    - top_market
  - chart:
    - months
    - values
  - table:
    - rows
    - page
    - pages
    - total
    - per_page

Pagination server-side bằng `.paginate()`.

#### `POST /api/upload`

- Admin/Manager.
- Nhận file Excel.
- Validate extension:
  - `.xlsx`
  - `.xlsm`
  - `.xls`
- Save file vào `uploads/` với timestamp prefix.
- Gọi `process_excel(file_path)`.
- Nếu lỗi ETL:
  - ghi `UPLOAD_LOGS` status `fail`.
  - trả 400 JSON.
- Nếu lỗi unexpected:
  - rollback DB.
  - ghi log fail.
  - trả 500 JSON.
- Nếu success:
  - ghi `UPLOAD_LOGS` status `success`.
  - trả result summary.

#### `POST /upload`

- Form fallback route.
- Gọi lại `api_upload()`.
- Flash message.
- Redirect về upload page.

#### `GET /api/export`

- Admin/Manager.
- Gọi `build_export_workbook()`.
- Trả file Excel download.

#### `GET /api/upload-logs`

- Admin/Manager.
- Trả upload logs dạng JSON.
- Có pagination.

#### `GET /api/admin/tables`

- Chỉ Admin.
- Trả danh sách table registry.

#### `GET /api/admin/table-data`

- Chỉ Admin.
- Query table bất kỳ trong registry.
- Params:
  - `table`
  - `page`
  - `per_page`
  - `search`
  - `sort_col`
  - `sort_dir`
  - riêng `FACT_ETD`:
    - `month`
    - `customer_id`
    - `market_id`
- DIM/users:
  - search trên các column text bằng `ilike`.
- Sort:
  - chỉ sort nếu `sort_col` nằm trong column list thật.

#### `POST /api/admin/sql`

- Chỉ Admin.
- Nhận JSON:

```json
{"sql": "SELECT * FROM FACT_ETD LIMIT 100"}
```

- Chỉ cho SELECT.
- Không cho multi statement có `;`.
- Chặn keyword nguy hiểm.
- Execute bằng `db.session.execute(text(sql))`.
- Fetch tối đa 500 rows.

Security caveat:

- Validation SELECT-only hiện ở mức keyword/string. Tốt hơn production nên dùng parser SQL hoặc whitelist query builder.

### 5.6 `export_service.py`

Vai trò:

- Xuất dữ liệu database ra Excel nhiều sheet.

Function:

```python
build_export_workbook()
```

Flow:

1. Tạo `BytesIO`.
2. Khai báo `sheets` dict gồm query và columns.
3. Dùng `pd.ExcelWriter(output, engine="openpyxl")`.
4. Ghi từng DataFrame vào sheet.
5. Return `BytesIO`.

Sheets:

- `FACT_ETD`
- `DIM_Customer`
- `DIM_Type`
- `DIM_Laser`
- `DIM_CountryOfMaker`
- `DIM_CarMaker`
- `DIM_Country`
- `DIM_Market`
- `DIM_Type2`

Hiện chưa export `users` và `UPLOAD_LOGS`.

## 6. Templates

### 6.1 `templates/base.html`

Layout gốc cho toàn bộ trang.

Chứa:

- Bootstrap 5 CDN.
- `meta[name="csrf-token"]`.
- Link `static/css/app.css`.
- Sidebar khi user authenticated.
- Menu theo role:
  - Dashboard: mọi user.
  - Upload Excel, Upload History: Admin/Manager.
  - Data Explorer, Users: Admin.
  - Change Password: mọi user.
- Topbar:
  - Dark mode button.
  - Export Excel chỉ Admin/Manager.
- Render flash messages.
- Include Bootstrap JS và `static/js/app.js`.

### 6.2 `templates/login.html`

Trang login.

Form fields:

- username
- password
- `_csrf_token`

Hiển thị hint seed account `admin / admin123`.

### 6.3 `templates/dashboard.html`

Trang dashboard chính.

Layout:

- Left filter sidebar:
  - Customer
  - Type
  - Country
  - CarMaker
  - Market
  - Month from
  - Month to
  - Reset
  - Upload button cho Admin/Manager
- Right content:
  - loading spinner overlay.
  - KPI cards:
    - Total Value
    - Total PartNo
    - Total Customer
    - Total Market
  - info cards:
    - Top Customer
    - Top Market
  - Plotly bar chart.
  - FACT preview table.
  - pagination buttons.

JS dùng: `static/js/dashboard.js`.

### 6.4 `templates/upload.html`

Trang upload Excel.

Form:

- file input accept `.xlsx,.xls,.xlsm`
- CSRF hidden input

Sau upload AJAX thành công:

- Hiển thị Bootstrap modal `Upload completed`.
- Summary:
  - Total rows
  - Inserted
  - Updated
  - Skipped
  - Invalid rows
  - Detected header row

JS dùng: `static/js/upload.js`.

### 6.5 `templates/upload_history.html`

Trang lịch sử upload.

Chứa table render bằng AJAX từ `/api/upload-logs`.

Features:

- total rows display.
- pagination Previous/Next.

JS dùng: `static/js/upload_history.js`.

### 6.6 `templates/data_explorer.html`

Admin Data Explorer.

Chỉ Admin vào được route.

Giao diện có 2 tab:

#### Tab Tables

Left sidebar:

- list tables:
  - FACT_ETD
  - DIM_Customer
  - DIM_Type
  - DIM_Laser
  - DIM_CountryOfMaker
  - DIM_Country
  - DIM_CarMaker
  - DIM_Market
  - DIM_Type2
  - users
  - UPLOAD_LOGS

Right content:

- Search input.
- FACT-only filters:
  - Month
  - CustomerID
  - MarketID
- Apply button.
- Grid table.
- pagination.
- sortable headers.

DataTables.js được include nhưng paging/search/order của DataTables bị tắt, vì app đang dùng server-side pagination/search/sort tự viết.

#### Tab SQL Console

- Textarea SQL.
- Button `Run SELECT`.
- Result table.

JS dùng: `static/js/data_explorer.js`.

### 6.7 `templates/users.html`

Trang quản lý user, chỉ Admin.

Create user form:

- Username
- Full name
- Employee code
- Password
- Role
- Manager

Accounts table:

- Username readonly.
- Employee code editable.
- Full name editable.
- Role editable.
- Manager editable.
- Active checkbox.
- New password field optional.
- Save button.
- Delete button.

Admin có thể gán user thuộc manager/admin nào qua dropdown manager.

### 6.8 `templates/change_password.html`

Trang đổi mật khẩu cho user đang login.

Fields:

- Current password.
- New password.
- Confirm new password.

Submit POST về cùng route `/change-password`.

### 6.9 `templates/error.html`

Trang lỗi dùng cho 403, 404, 413.

Nếu user authenticated:

- Hiển thị trong app layout.

Nếu chưa authenticated:

- Hiển thị trong public login style.

### 6.10 `templates/_flash.html`

Partial hiển thị Flask flash messages bằng Bootstrap alert.

## 7. Static JavaScript

### 7.1 `static/js/app.js`

Vai trò:

- Dark mode toggle.
- Lưu theme vào `localStorage` key `dashboard-theme`.
- Set `data-bs-theme` trên `<html>`.
- Toggle class `dark-mode` trên body.
- Dispatch resize để Plotly resize chart.

### 7.2 `static/js/dashboard.js`

Vai trò:

- Load filter dropdowns từ `/api/filter`.
- Load dashboard data từ `/api/dashboard`.
- Render KPI.
- Render Plotly bar chart.
- Render FACT preview table.
- Handle server-side pagination.
- Handle filter changes.
- Show loading spinner.

Quan trọng:

- `selectOptions()` xử lý cả item object `{id, text}` và primitive string.
- Nếu text rỗng thì hiện `(blank)` để tránh `[object Object]`.

Dashboard API params:

- customer_id
- type_id
- country_id
- car_maker_id
- market_id
- month_from
- month_to
- page
- per_page

### 7.3 `static/js/upload.js`

Vai trò:

- Intercept upload form submit.
- Gửi file bằng `fetch("/api/upload", {method: "POST", body: FormData})`.
- Gửi CSRF header `X-CSRFToken`.
- Disable button khi processing.
- Hiển thị alert success/fail.
- Nếu success:
  - reset form.
  - render upload summary modal.

### 7.4 `static/js/upload_history.js`

Vai trò:

- Load `/api/upload-logs`.
- Render generic table.
- Handle pagination.

State:

```js
historyState = { page: 1, perPage: 25 }
```

### 7.5 `static/js/data_explorer.js`

Vai trò:

- Handle Admin Data Explorer.
- Switch table khi click table list.
- Load table data AJAX từ `/api/admin/table-data`.
- Apply search/filter/sort/pagination.
- Run SQL console via `/api/admin/sql`.

State:

```js
explorer = {
  table: "FACT_ETD",
  page: 1,
  perPage: 25,
  sortCol: "",
  sortDir: "asc",
}
```

Security:

- SQL request gửi CSRF header.
- Backend vẫn là nơi validate SELECT-only.

## 8. Static CSS

### `static/css/app.css`

Chứa toàn bộ styling custom.

Thiết kế:

- Sidebar dark gray.
- Blue accent.
- Corporate BI dashboard style.
- Bootstrap panels/cards.
- Responsive layout.
- Dark mode basic.

Key classes:

- `.app-shell`: grid layout sidebar + main.
- `.app-sidebar`: sidebar fixed/sticky.
- `.topbar`: header.
- `.content-wrap`: main content padding.
- `.filter-panel`
- `.chart-panel`
- `.table-panel`
- `.form-panel`
- `.upload-panel`
- `.kpi-card`
- `.info-card`
- `.loading-overlay`
- `.table-list`
- `.sql-editor`

Responsive:

- At max-width 992px, layout collapses to single column.
- Sidebar no longer fixed height.

## 9. Database Design

### 9.1 Fact/DIM Model

Business design:

- `PartNo` là business key, không tạo DIM.
- Text attributes tạo DIM riêng.
- FACT lưu surrogate key IDs.

FACT unique:

```text
PartNo + Month
```

Mapping:

| Excel Column | Database |
|---|---|
| Customer | DIM_Customer.CustomerID |
| Type | DIM_Type.TypeID |
| Laser | DIM_Laser.LaserID |
| Country of maker | DIM_CountryOfMaker.CountryOfMakerID |
| Car maker | DIM_CarMaker.CarMakerID |
| Column1 / Country | DIM_Country.CountryID |
| Market / Market (easy) | DIM_Market.MarketID |
| Type2 | DIM_Type2.Type2ID |
| Part No. | FACT_ETD.PartNo |
| Month columns | FACT_ETD.Month |
| Cell value | FACT_ETD.Value |

### 9.2 User/Manager Model

Self-reference relationship:

```text
users.manager_id -> users.id
```

Use cases:

- 1 manager/admin có nhiều staff.
- Admin chỉnh manager của user ở `/users`.
- `staff_members` relationship dùng để lấy danh sách nhân viên thuộc manager.

Hiện chưa có dashboard riêng theo manager-staff. Nếu cần phân quyền dữ liệu theo manager, phải bổ sung filter theo user ownership hoặc mapping dữ liệu phụ trách.

## 10. ETL Data Rules

Input Excel được đọc dynamic, không hardcode row number.

Header detection:

- Tìm row chứa đủ:
  - Customer
  - Type
  - Part No.
  - Laser
  - Country of maker
  - Car maker
  - Market
  - Type2

Main table detection:

- Sau header, scan từng dòng.
- Skip:
  - toàn null.
  - Part No invalid.
  - không có month numeric data.
- Stop:
  - Customer null liên tiếp sau khi data bắt đầu.
  - Part No null sau khi data bắt đầu.
  - gặp garbage marker sau khi data bắt đầu.

Part No valid:

```text
^[A-Z0-9\-]+$
```

Value clean:

- `"76,032"` -> `76032`.
- `"-"` -> empty -> drop.
- non-numeric -> drop.

Duplicate handling:

- Existing FACT by `PartNo + Month`.
- Nếu payload khác: update.
- Nếu payload giống: skipped.
- Nếu chưa có: insert.

## 11. API Summary

Auth/UI:

```text
GET  /
GET  /login
POST /login
POST /logout
GET  /change-password
POST /change-password
GET  /users
POST /users/create
POST /users/<id>/update
POST /users/<id>/delete
```

Dashboard/upload/export:

```text
GET  /dashboard
GET  /upload
POST /upload
GET  /upload-history
GET  /api/filter
GET  /api/dashboard
POST /api/upload
GET  /api/export
GET  /api/upload-logs
```

Admin explorer:

```text
GET  /admin/data-explorer
GET  /api/admin/tables
GET  /api/admin/table-data
POST /api/admin/sql
```

## 12. Chạy Project

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Nếu máy không nhận `python`, dùng:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -3 app.py
```

Open:

```text
http://127.0.0.1:5000
```

## 13. Requirements

`requirements.txt` hiện gồm:

```text
Flask==3.0.3
Flask-Login==0.6.3
Flask-SQLAlchemy==3.1.1
pandas==2.2.3
openpyxl==3.1.5
SQLAlchemy==2.0.36
Werkzeug==3.0.6
xlrd==2.0.1
```

Ghi chú:

- `openpyxl` dùng đọc/ghi `.xlsx`.
- `xlrd` hỗ trợ đọc `.xls` tùy trường hợp.
- Plotly, Bootstrap, DataTables đang dùng CDN trong templates, không nằm trong pip requirements.

## 14. Testing Đã Làm Trong Quá Trình Phát Triển

Đã test bằng Flask test client:

- Login admin/manager/staff/user 90122.
- `/dashboard` render.
- `/api/filter` OK.
- `/api/dashboard` OK.
- `/upload` Admin/Manager OK.
- Manager bị chặn khỏi `/admin/data-explorer`.
- Admin vào `/admin/data-explorer` OK.
- SQL SELECT OK.
- SQL DROP bị chặn.
- User 90122 đổi mật khẩu OK, sau đó reset về `123`.
- `/users` render OK.

Đã test ETL với file thực tế:

```text
c:\Users\zoxy4\Downloads\Actual.FY2024.1.ETD.detail.xlsx
```

Kết quả quan trọng:

- Detect header row dynamic.
- Không lấy vùng rác phía dưới như `FC`, `vs AP`, `RAP`, `Amount`.
- `Column1` map vào `DIM_Country`.
- Upload lại file y nguyên không duplicate, rows thành skipped.
- Nếu sửa một value trong file mới, upload sẽ update đúng 1 FACT row.

## 15. Known Issues / Cần Cải Thiện

1. Không dùng Alembic.
   - Hiện migration viết tay trong `ensure_schema()`.
   - Nên chuyển sang Flask-Migrate nếu project lớn hơn.

2. SQL Console validation còn đơn giản.
   - Hiện chặn bằng prefix SELECT và forbidden keywords.
   - Production nên dùng SQL parser hoặc chỉ cho query builder whitelist.

3. Manager-staff relationship mới chỉ quản lý user.
   - Chưa áp dụng vào business data visibility.
   - Nếu cần Manager chỉ thấy dữ liệu staff mình phụ trách, phải thêm mapping dữ liệu theo user/staff.

4. Upload invalid rows summary đang cộng cả source invalid rows và dropped fact cells.
   - Có thể tách riêng để báo cáo rõ hơn.

5. Export chưa gồm `users` và `UPLOAD_LOGS`.
   - Nếu cần audit export, bổ sung trong `export_service.py`.

6. CDN dependencies.
   - Bootstrap/Plotly/DataTables dùng CDN.
   - Môi trường offline cần vendor static files local.

7. SECRET_KEY mặc định random.
   - Production cần set env `SECRET_KEY` cố định.

8. SQLite không phù hợp multi-user write-heavy.
   - Nếu nhiều người upload đồng thời, nên chuyển PostgreSQL/MySQL.

## 16. Gợi Ý Task Tiếp Theo

Các task hợp lý để AI/dev khác tiếp tục:

1. Thêm Flask-Migrate/Alembic và bỏ migration thủ công.
2. Thêm audit log cho user CRUD và change password.
3. Thêm manager dashboard: manager xem danh sách staff thuộc mình.
4. Thêm data permission theo manager/staff nếu có nghiệp vụ phân quyền dữ liệu.
5. Tách API response chuẩn `{ok, message, data}` đồng nhất.
6. Thêm unit tests cho ETL:
   - detect header.
   - ignore garbage rows.
   - Column1 -> Country.
   - update existing FACT.
7. Thêm bulk delete/reset data screen cho Admin.
8. Thêm option upload mode:
   - append/update.
   - reset FACT/DIM before import.
9. Đưa Bootstrap/Plotly/DataTables về local static để chạy offline.
10. Thêm Dockerfile và production WSGI server như Waitress/Gunicorn.

## 17. Quick Mental Model Cho AI Tiếp Theo

Nếu cần sửa ETL:

- Bắt đầu từ `etl.py`.
- Đọc `_extract_main_table()` trước.
- Header aliases nằm ở `COLUMN_ALIASES`.
- Garbage logic nằm ở `GARBAGE_REGEX`.
- Valid Part No nằm ở `_valid_part_no()`.
- Insert/update logic nằm trong `process_excel()`.

Nếu cần sửa dashboard:

- Backend API ở `dashboard.py`.
- HTML ở `templates/dashboard.html`.
- Frontend fetch/render ở `static/js/dashboard.js`.

Nếu cần sửa user/role:

- Schema ở `models.py` class `User`.
- Auth routes ở `auth.py`.
- UI ở `templates/users.html` và `templates/change_password.html`.

Nếu cần sửa Admin Explorer:

- Route/API ở `dashboard.py`:
  - `data_explorer()`
  - `api_admin_table_data()`
  - `api_admin_sql()`
- HTML ở `templates/data_explorer.html`.
- JS ở `static/js/data_explorer.js`.

Nếu cần sửa export:

- `export_service.py`.

Nếu cần sửa layout/theme:

- `templates/base.html`.
- `static/css/app.css`.
- `static/js/app.js`.
