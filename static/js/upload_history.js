const historyState = { page: 1, perPage: 25 };

function renderGenericTable(headId, bodyId, columns, rows) {
  document.getElementById(headId).innerHTML = columns.map((col) => `<th>${col}</th>`).join("");
  document.getElementById(bodyId).innerHTML = rows.length
    ? rows.map((row) => `<tr>${columns.map((col) => `<td>${row[col] ?? ""}</td>`).join("")}</tr>`).join("")
    : `<tr><td colspan="${Math.max(columns.length, 1)}" class="text-center text-secondary py-4">No data</td></tr>`;
}

async function loadHistory() {
  const params = new URLSearchParams({ page: historyState.page, per_page: historyState.perPage });
  const response = await fetch(`/api/upload-logs?${params}`);
  const data = await response.json();
  renderGenericTable("historyHead", "historyBody", data.columns, data.rows);
  document.getElementById("historyMeta").textContent = `${data.total} rows`;
  document.getElementById("historyPageInfo").textContent = `Page ${data.page} / ${Math.max(data.pages, 1)}`;
  document.getElementById("historyPrev").disabled = data.page <= 1;
  document.getElementById("historyNext").disabled = data.page >= data.pages;
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("historyPrev").addEventListener("click", () => {
    historyState.page -= 1;
    loadHistory();
  });
  document.getElementById("historyNext").addEventListener("click", () => {
    historyState.page += 1;
    loadHistory();
  });
  loadHistory();
});
