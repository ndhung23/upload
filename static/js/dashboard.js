const state = {
  page: 1,
  perPage: 25,
};

const moneyFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 0,
});

function csrfToken() {
  return document.querySelector('meta[name="csrf-token"]').content;
}

function selectOptions(select, items, placeholder) {
  select.innerHTML = `<option value="">${placeholder}</option>`;
  items.forEach((item) => {
    const option = document.createElement("option");
    const isObject = item !== null && typeof item === "object";
    option.value = isObject && Object.prototype.hasOwnProperty.call(item, "id") ? item.id : item;
    option.textContent = isObject && Object.prototype.hasOwnProperty.call(item, "text") ? (item.text || "(blank)") : item;
    select.appendChild(option);
  });
}

function filters() {
  return {
    upload_log_id: document.getElementById("uploadFilter").value,
    compare_upload_id: document.getElementById("compareUploadFilter").value,
    chart_type: document.getElementById("chartTypeFilter").value,
    fiscal_year: document.getElementById("fyFilter").value,
    customer_id: document.getElementById("customerFilter").value,
    type_id: document.getElementById("typeFilter").value,
    country_id: document.getElementById("countryFilter").value,
    car_maker_id: document.getElementById("carMakerFilter").value,
    market_id: document.getElementById("marketFilter").value,
    month_from: document.getElementById("monthFromFilter").value,
    month_to: document.getElementById("monthToFilter").value,
    page: state.page,
    per_page: state.perPage,
  };
}

function queryString(params) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== "" && value !== null && value !== undefined) search.set(key, value);
  });
  return search.toString();
}

function showAlert(message, type = "danger") {
  document.getElementById("dashboardAlert").innerHTML = `
    <div class="alert alert-${type} alert-dismissible fade show" role="alert">
      ${message}
      <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    </div>`;
}

async function loadFilters() {
  const response = await fetch("/api/filter", {
    headers: { "X-CSRFToken": csrfToken() },
  });
  const data = await response.json();
  selectOptions(document.getElementById("uploadFilter"), data.uploads, "All uploaded files");
  selectOptions(document.getElementById("compareUploadFilter"), data.uploads, "Compare with file");
  selectOptions(document.getElementById("fyFilter"), data.fiscal_years, "All fiscal years");
  selectOptions(document.getElementById("customerFilter"), data.customers, "All customers");
  selectOptions(document.getElementById("typeFilter"), data.types, "All types");
  selectOptions(document.getElementById("countryFilter"), data.countries, "All countries");
  selectOptions(document.getElementById("carMakerFilter"), data.car_makers, "All car makers");
  selectOptions(document.getElementById("marketFilter"), data.markets, "All markets");
  selectOptions(document.getElementById("monthFromFilter"), data.months, "Start");
  selectOptions(document.getElementById("monthToFilter"), data.months, "End");
}

function renderChart(chart) {
  const isDark = document.body.classList.contains("dark-mode");
  const traces = [];
  const layout = {
    margin: { t: 20, r: 20, l: 70, b: 60 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: isDark ? "#e5e7eb" : "#0f172a" },
    xaxis: { gridcolor: isDark ? "#334155" : "#e2e8f0" },
    yaxis: { gridcolor: isDark ? "#334155" : "#e2e8f0", tickformat: "," },
    responsive: true,
  };

  if (chart.type === "pie") {
    traces.push({
      labels: chart.pie_labels,
      values: chart.pie_values,
      type: "pie",
      hole: 0.35,
      hovertemplate: "%{label}<br>%{value:,.0f}<extra></extra>",
    });
    layout.margin = { t: 20, r: 20, l: 20, b: 20 };
  } else if (chart.type === "line") {
    traces.push({
      x: chart.months,
      y: chart.values,
      type: "scatter",
      mode: "lines+markers",
      name: "Selected file",
      line: { color: "#2563eb", width: 3 },
      hovertemplate: "%{x}<br>%{y:,.0f}<extra></extra>",
    });
  } else if (chart.type === "yamazumi") {
    chart.stacked_series.forEach((series) => {
      traces.push({
        x: chart.stacked_months,
        y: series.values,
        type: "bar",
        name: series.name,
        hovertemplate: "%{x}<br>%{fullData.name}: %{y:,.0f}<extra></extra>",
      });
    });
    layout.barmode = "stack";
  } else {
    traces.push({
      x: chart.months,
      y: chart.values,
      type: "bar",
      name: "Selected file",
      marker: { color: "#2563eb" },
      hovertemplate: "%{x}<br>%{y:,.0f}<extra></extra>",
    });
  }

  if (chart.compare && chart.type !== "pie" && chart.type !== "yamazumi") {
    traces.push({
      x: chart.compare.months,
      y: chart.compare.values,
      type: chart.type === "line" ? "scatter" : "bar",
      mode: chart.type === "line" ? "lines+markers" : undefined,
      name: "Compare file",
      marker: { color: "#f59e0b" },
      line: { color: "#f59e0b", width: 3 },
      hovertemplate: "%{x}<br>%{y:,.0f}<extra></extra>",
    });
    if (chart.type === "bar") layout.barmode = "group";
  }

  Plotly.newPlot(
    "barChart",
    traces,
    layout,
    { displayModeBar: false, responsive: true },
  );
}

function renderTable(table) {
  const body = document.getElementById("factTableBody");
  body.innerHTML = "";

  if (!table.rows.length) {
    body.innerHTML = `<tr><td colspan="8" class="text-center text-secondary py-4">No data</td></tr>`;
  } else {
    table.rows.forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${row.PartNo}</td>
        <td>${row.Customer}</td>
        <td>${row.Type}</td>
        <td>${row.Country}</td>
        <td>${row.CarMaker}</td>
        <td>${row.Market}</td>
        <td>${row.Month}</td>
        <td class="text-end">${moneyFormatter.format(row.Value)}</td>`;
      body.appendChild(tr);
    });
  }

  document.getElementById("tableMeta").textContent = `${moneyFormatter.format(table.total)} rows`;
  document.getElementById("pageInfo").textContent = `Page ${table.page} / ${Math.max(table.pages, 1)}`;
  document.getElementById("prevPage").disabled = table.page <= 1;
  document.getElementById("nextPage").disabled = table.page >= table.pages;
}

async function loadDashboard() {
  const loading = document.getElementById("dashboardLoading");
  if (loading) loading.classList.remove("d-none");
  const response = await fetch(`/api/dashboard?${queryString(filters())}`, {
    headers: { "X-CSRFToken": csrfToken() },
  });
  if (!response.ok) {
    showAlert("Cannot load dashboard data");
    if (loading) loading.classList.add("d-none");
    return;
  }
  const data = await response.json();
  document.getElementById("totalValue").textContent = moneyFormatter.format(data.stats.total_value);
  document.getElementById("totalPartNo").textContent = moneyFormatter.format(data.stats.total_part_no);
  document.getElementById("totalCustomer").textContent = moneyFormatter.format(data.stats.total_customer);
  document.getElementById("totalMarket").textContent = moneyFormatter.format(data.stats.total_market);
  document.getElementById("topCustomer").textContent = data.stats.top_customer;
  document.getElementById("topMarket").textContent = data.stats.top_market;
  renderChart(data.chart);
  renderTable(data.table);
  if (loading) loading.classList.add("d-none");
}

function bindEvents() {
  [
    "customerFilter",
    "uploadFilter",
    "compareUploadFilter",
    "chartTypeFilter",
    "fyFilter",
    "typeFilter",
    "countryFilter",
    "carMakerFilter",
    "marketFilter",
    "monthFromFilter",
    "monthToFilter",
  ].forEach((id) => {
    document.getElementById(id).addEventListener("change", () => {
      state.page = 1;
      loadDashboard();
    });
  });

  document.getElementById("resetFilters").addEventListener("click", () => {
    document.querySelectorAll(".filter-panel select").forEach((select) => {
      select.value = "";
    });
    state.page = 1;
    loadDashboard();
  });

  document.getElementById("prevPage").addEventListener("click", () => {
    state.page -= 1;
    loadDashboard();
  });

  document.getElementById("nextPage").addEventListener("click", () => {
    state.page += 1;
    loadDashboard();
  });

  window.addEventListener("resize", () => {
    Plotly.Plots.resize(document.getElementById("barChart"));
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    await loadFilters();
    bindEvents();
    await loadDashboard();
  } catch (error) {
    showAlert(error.message || "Dashboard initialization failed");
  }
});
