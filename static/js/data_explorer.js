const explorer = {
  table: "FACT_ETD",
  page: 1,
  perPage: 25,
  sortCol: "",
  sortDir: "asc",
};
let explorerDataTable = null;

function token() {
  return document.querySelector('meta[name="csrf-token"]').content;
}

function params(obj) {
  const search = new URLSearchParams();
  Object.entries(obj).forEach(([key, value]) => {
    if (value !== "" && value !== undefined && value !== null) search.set(key, value);
  });
  return search.toString();
}

function html(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderTable(columns, rows) {
  if (explorerDataTable) {
    explorerDataTable.destroy();
    explorerDataTable = null;
  }
  document.getElementById("explorerHead").innerHTML = columns
    .map((col) => `<th><button class="btn btn-link btn-sm p-0 explorer-sort" data-col="${html(col)}">${html(col)}</button></th>`)
    .join("");
  document.getElementById("explorerBody").innerHTML = rows.length
    ? rows.map((row) => `<tr>${columns.map((col) => `<td>${html(row[col])}</td>`).join("")}</tr>`).join("")
    : `<tr><td colspan="${Math.max(columns.length, 1)}" class="text-center text-secondary py-4">No data</td></tr>`;

  document.querySelectorAll(".explorer-sort").forEach((button) => {
    button.addEventListener("click", () => {
      const col = button.dataset.col;
      explorer.sortDir = explorer.sortCol === col && explorer.sortDir === "asc" ? "desc" : "asc";
      explorer.sortCol = col;
      explorer.page = 1;
      loadExplorer();
    });
  });

  if (window.DataTable) {
    explorerDataTable = new DataTable("#explorerTable", {
      paging: false,
      searching: false,
      ordering: false,
      info: false,
      destroy: true,
    });
  }
}

async function loadExplorer() {
  const isFact = explorer.table === "FACT_ETD";
  document.querySelectorAll(".fact-filter").forEach((el) => el.classList.toggle("d-none", !isFact));
  const query = {
    table: explorer.table,
    page: explorer.page,
    per_page: explorer.perPage,
    search: document.getElementById("explorerSearch").value,
    month: document.getElementById("explorerMonth").value,
    customer_id: document.getElementById("explorerCustomerID").value,
    market_id: document.getElementById("explorerMarketID").value,
    sort_col: explorer.sortCol,
    sort_dir: explorer.sortDir,
  };
  const response = await fetch(`/api/admin/table-data?${params(query)}`);
  const data = await response.json();
  if (!data.ok) {
    document.getElementById("explorerMeta").textContent = data.message || "Cannot load table";
    return;
  }
  renderTable(data.columns, data.rows);
  document.getElementById("explorerMeta").textContent = `${data.table}: ${data.total} rows`;
  document.getElementById("explorerPageInfo").textContent = `Page ${data.page} / ${Math.max(data.pages, 1)}`;
  document.getElementById("explorerPrev").disabled = data.page <= 1;
  document.getElementById("explorerNext").disabled = data.page >= data.pages;
}

async function runSql() {
  const status = document.getElementById("sqlStatus");
  status.textContent = "Running...";
  const response = await fetch("/api/admin/sql", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": token(),
    },
    body: JSON.stringify({ sql: document.getElementById("sqlInput").value }),
  });
  const data = await response.json();
  if (!data.ok) {
    status.textContent = data.message || "SQL failed";
    document.getElementById("sqlHead").innerHTML = "";
    document.getElementById("sqlBody").innerHTML = "";
    return;
  }
  document.getElementById("sqlHead").innerHTML = data.columns.map((col) => `<th>${html(col)}</th>`).join("");
  document.getElementById("sqlBody").innerHTML = data.rows.length
    ? data.rows.map((row) => `<tr>${data.columns.map((col) => `<td>${html(row[col])}</td>`).join("")}</tr>`).join("")
    : `<tr><td colspan="${Math.max(data.columns.length, 1)}" class="text-center text-secondary py-4">No data</td></tr>`;
  status.textContent = `${data.total} rows returned`;
}

document.addEventListener("DOMContentLoaded", () => {
  const first = document.querySelector("#tableList button.active");
  explorer.table = first ? first.dataset.table : "FACT_ETD";

  document.querySelectorAll("#tableList button").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("#tableList button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      explorer.table = button.dataset.table;
      explorer.page = 1;
      explorer.sortCol = "";
      loadExplorer();
    });
  });

  document.getElementById("explorerApply").addEventListener("click", () => {
    explorer.page = 1;
    loadExplorer();
  });
  document.getElementById("explorerSearch").addEventListener("input", () => {
    explorer.page = 1;
    loadExplorer();
  });
  document.getElementById("explorerPrev").addEventListener("click", () => {
    explorer.page -= 1;
    loadExplorer();
  });
  document.getElementById("explorerNext").addEventListener("click", () => {
    explorer.page += 1;
    loadExplorer();
  });
  document.getElementById("runSql").addEventListener("click", runSql);
  loadExplorer();
});
