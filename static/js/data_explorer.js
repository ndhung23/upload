const dataState = {
  page: 1,
  perPage: 30,
  options: {},
  hiddenColumns: new Set(JSON.parse(localStorage.getItem("data-hidden-columns") || "[]")),
  baseColumns: [
    ["PartNo", "PartNo"],
    ["Customer", "Customer"],
    ["Type", "Type"],
    ["Type2", "Type2"],
    ["Laser", "Laser"],
    ["CountryOfMaker", "Country maker"],
    ["CarMaker", "Car maker"],
    ["Country", "Country"],
    ["Market", "Market"],
  ],
};

function token() {
  return document.querySelector('meta[name="csrf-token"]').content;
}

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function fillSelect(id, items, placeholder) {
  const select = document.getElementById(id);
  select.innerHTML = `<option value="">${placeholder}</option>`;
  items.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.id ?? item;
    option.textContent = item.text ?? item;
    select.appendChild(option);
  });
}

async function loadOptions() {
  const response = await fetch("/api/data/options", { headers: { "X-CSRFToken": token() } });
  dataState.options = await response.json();
  fillSelect("dataFileCategoryFilter", dataState.options.file_categories, "All file types");
  fillSelect("dataMonthFrom", dataState.options.months, "Start");
  fillSelect("dataMonthTo", dataState.options.months, "End");
  fillSelect("dataYearFilter", dataState.options.years, "All years");
  fillSelect("dataCustomerFilter", dataState.options.customers, "All customers");
  fillSelect("dataTypeFilter", dataState.options.types, "All types");
  fillSelect("dataType2Filter", dataState.options.type2s, "All type2");
  fillSelect("dataLaserFilter", dataState.options.lasers, "All lasers");
  fillSelect("dataCountryMakerFilter", dataState.options.country_of_makers, "All country makers");
  fillSelect("dataCountryFilter", dataState.options.countries, "All countries");
  fillSelect("dataMarketFilter", dataState.options.markets, "All markets");
  fillSelect("dataCarMakerFilter", dataState.options.car_makers, "All car makers");
  if (dataState.options.months.length) {
    document.getElementById("dataMonthFrom").value = dataState.options.months[0];
    document.getElementById("dataMonthTo").value = dataState.options.months[Math.min(dataState.options.months.length - 1, 11)];
  }
  initPartModalOptions();
  renderColumnToggles();
}

function queryString() {
  const params = new URLSearchParams({ page: dataState.page, per_page: dataState.perPage });
  [
    ["file_category", "dataFileCategoryFilter"],
    ["month_from", "dataMonthFrom"],
    ["month_to", "dataMonthTo"],
    ["fiscal_year", "dataYearFilter"],
    ["customer_id", "dataCustomerFilter"],
    ["type_id", "dataTypeFilter"],
    ["type2_id", "dataType2Filter"],
    ["laser_id", "dataLaserFilter"],
    ["country_maker_id", "dataCountryMakerFilter"],
    ["country_id", "dataCountryFilter"],
    ["market_id", "dataMarketFilter"],
    ["car_maker_id", "dataCarMakerFilter"],
    ["search", "dataSearch"],
  ].forEach(([key, id]) => {
    const value = document.getElementById(id).value;
    if (value) params.set(key, value);
  });
  return params.toString();
}

function renderHead(months) {
  const visibleBase = dataState.baseColumns.filter(([key]) => !dataState.hiddenColumns.has(key));
  document.getElementById("dataHead").innerHTML = `
    <tr>
      ${visibleBase.map(([key, label], index) => `<th class="${index === 0 ? "sticky-info" : ""}" data-col="${key}">${label}</th>`).join("")}
      ${months.map((month) => `<th class="month-col">${esc(month)}</th>`).join("")}
    </tr>`;
}

function rowDataset(row, month) {
  return [
    ["UploadLogID", row.UploadLogID],
    ["PartNo", row.PartNo],
    ["CustomerID", row.CustomerID],
    ["TypeID", row.TypeID],
    ["Type2ID", row.Type2ID],
    ["LaserID", row.LaserID],
    ["CountryOfMakerID", row.CountryOfMakerID],
    ["CarMakerID", row.CarMakerID],
    ["CountryID", row.CountryID],
    ["MarketID", row.MarketID],
    ["month", month],
  ].map(([key, value]) => `data-${key.toLowerCase()}="${esc(value)}"`).join(" ");
}

function renderRows(rows, months) {
  const visibleBase = dataState.baseColumns.filter(([key]) => !dataState.hiddenColumns.has(key));
  document.getElementById("dataBody").innerHTML = rows.length
    ? rows.map((row) => `
      <tr>
        ${visibleBase.map(([key], index) => {
          const value = key === "Type2" ? `<span class="badge text-bg-light">${esc(row[key])}</span>` : esc(row[key]);
          return `<td class="${index === 0 ? "sticky-info fw-semibold" : ""}" data-col="${key}">${value}</td>`;
        }).join("")}
        ${months.map((month) => {
          const cell = row.values[month] || {};
          return `<td class="month-cell">
            <input class="form-control form-control-sm matrix-value text-end" type="number" step="0.01"
              value="${esc(cell.value ?? "")}" data-original="${esc(cell.value ?? "")}" ${rowDataset(row, month)}
              title="${esc(cell.updated_by || "")} ${esc(cell.updated_at || "")}">
          </td>`;
        }).join("")}
      </tr>`).join("")
    : `<tr><td colspan="${Math.max(months.length + visibleBase.length, 1)}" class="text-center text-secondary py-4">No data</td></tr>`;
}

async function loadMatrix() {
  const response = await fetch(`/api/data/matrix?${queryString()}`, { headers: { "X-CSRFToken": token() } });
  const data = await response.json();
  renderHead(data.months || []);
  renderRows(data.rows || [], data.months || []);
  document.getElementById("dataMeta").textContent = `${data.total} part rows`;
  document.getElementById("dataPageInfo").textContent = `Page ${data.page} / ${Math.max(data.pages, 1)}`;
  document.getElementById("dataPrev").disabled = data.page <= 1;
  document.getElementById("dataNext").disabled = data.page >= data.pages;
}

function cellPayload(input) {
  return {
    UploadLogID: input.dataset.uploadlogid,
    PartNo: input.dataset.partno,
    CustomerID: input.dataset.customerid,
    TypeID: input.dataset.typeid,
    Type2ID: input.dataset.type2id,
    LaserID: input.dataset.laserid,
    CountryOfMakerID: input.dataset.countryofmakerid,
    CarMakerID: input.dataset.carmakerid,
    CountryID: input.dataset.countryid,
    MarketID: input.dataset.marketid,
    month: input.dataset.month,
    value: input.value || 0,
  };
}

async function saveCell(input) {
  if (input.value === input.dataset.original) return;
  input.classList.add("is-saving");
  const response = await fetch("/api/data/matrix-cell", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": token() },
    body: JSON.stringify(cellPayload(input)),
  });
  const data = await response.json();
  input.classList.remove("is-saving");
  if (!data.ok) {
    input.classList.add("is-invalid");
    alert(data.message || "Save failed");
    return;
  }
  input.dataset.original = input.value;
  input.classList.remove("is-invalid");
  input.classList.add("is-valid");
  setTimeout(() => input.classList.remove("is-valid"), 900);
}

function bindEvents() {
  ["dataFileCategoryFilter", "dataMonthFrom", "dataMonthTo", "dataCustomerFilter", "dataTypeFilter", "dataType2Filter", "dataLaserFilter", "dataCountryMakerFilter", "dataCountryFilter", "dataMarketFilter", "dataCarMakerFilter"].forEach((id) => {
    document.getElementById(id).addEventListener("change", () => {
      dataState.page = 1;
      loadMatrix();
    });
  });
  document.getElementById("dataYearFilter").addEventListener("change", () => {
    const year = document.getElementById("dataYearFilter").value.replace("FY", "");
    if (year) {
      const start = `${year}-Apr`;
      const end = `${String((Number(year) + 1) % 100).padStart(2, "0")}-Mar`;
      if (dataState.options.months.includes(start)) document.getElementById("dataMonthFrom").value = start;
      if (dataState.options.months.includes(end)) document.getElementById("dataMonthTo").value = end;
    }
    dataState.page = 1;
    loadMatrix();
  });
  document.getElementById("dataSearch").addEventListener("input", () => {
    dataState.page = 1;
    loadMatrix();
  });
  document.getElementById("dataApply").addEventListener("click", () => {
    dataState.page = 1;
    loadMatrix();
  });
  document.getElementById("dataClear").addEventListener("click", () => {
    document.querySelectorAll(".data-toolbar select, .data-toolbar input").forEach((field) => {
      field.value = "";
    });
    dataState.page = 1;
    loadMatrix();
  });
  document.getElementById("dataAddPart").addEventListener("click", openPartModal);
  document.getElementById("partSave").addEventListener("click", () => savePartRow());
  document.getElementById("dataPrev").addEventListener("click", () => {
    dataState.page -= 1;
    loadMatrix();
  });
  document.getElementById("dataNext").addEventListener("click", () => {
    dataState.page += 1;
    loadMatrix();
  });
  document.getElementById("dataBody").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target.classList.contains("matrix-value")) {
      event.preventDefault();
      saveCell(event.target);
    }
  });
  document.getElementById("dataBody").addEventListener("focusout", (event) => {
    if (event.target.classList.contains("matrix-value")) saveCell(event.target);
  });
}

function renderColumnToggles() {
  document.getElementById("columnToggles").innerHTML = dataState.baseColumns
    .map(([key, label]) => `
      <label class="form-check">
        <input class="form-check-input column-toggle" type="checkbox" value="${key}" ${dataState.hiddenColumns.has(key) ? "" : "checked"}>
        <span class="form-check-label">${label}</span>
      </label>`)
    .join("");
  document.querySelectorAll(".column-toggle").forEach((input) => {
    input.addEventListener("change", () => {
      if (input.checked) dataState.hiddenColumns.delete(input.value);
      else dataState.hiddenColumns.add(input.value);
      localStorage.setItem("data-hidden-columns", JSON.stringify([...dataState.hiddenColumns]));
      loadMatrix();
    });
  });
}

function fillFormSelect(name, items) {
  const select = document.querySelector(`#partForm [name="${name}"]`);
  select.innerHTML = optionHtml(items, "");
}

function optionHtml(items, selected) {
  return items.map((item) => `<option value="${esc(item.id ?? item)}" ${String(item.id ?? item) === String(selected) ? "selected" : ""}>${esc(item.text ?? item)}</option>`).join("");
}

function initPartModalOptions() {
  fillFormSelect("UploadLogID", dataState.options.uploads);
  fillFormSelect("Month", dataState.options.months.map((month) => ({ id: month, text: month })));
  fillFormSelect("CustomerID", dataState.options.customers);
  fillFormSelect("TypeID", dataState.options.types);
  fillFormSelect("Type2ID", dataState.options.type2s);
  fillFormSelect("LaserID", dataState.options.lasers);
  fillFormSelect("CountryOfMakerID", dataState.options.country_of_makers);
  fillFormSelect("CarMakerID", dataState.options.car_makers);
  fillFormSelect("CountryID", dataState.options.countries);
  fillFormSelect("MarketID", dataState.options.markets);
}

function openPartModal() {
  const form = document.getElementById("partForm");
  form.reset();
  const month = document.getElementById("dataMonthTo").value || document.getElementById("dataMonthFrom").value;
  if (month) form.elements.Month.value = month;
  new bootstrap.Modal(document.getElementById("partModal")).show();
}

async function savePartRow(force = false) {
  const form = document.getElementById("partForm");
  if (!form.checkValidity()) {
    form.reportValidity();
    return;
  }
  const payload = Object.fromEntries(new FormData(form).entries());
  if (force) payload.force = true;
  const response = await fetch("/api/data/matrix-row", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": token() },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!data.ok) {
    if (data.duplicate_partno) {
      if (confirm(data.message)) {
        savePartRow(true);
      }
      return;
    }
    alert(data.message || "Create failed");
    return;
  }
  bootstrap.Modal.getInstance(document.getElementById("partModal")).hide();
  dataState.page = 1;
  loadMatrix();
}

document.addEventListener("DOMContentLoaded", async () => {
  await loadOptions();
  bindEvents();
  await loadMatrix();
});
