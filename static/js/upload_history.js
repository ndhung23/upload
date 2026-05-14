const historyState = { page: 1, perPage: 25 };

function csrfToken() {
  return document.querySelector('meta[name="csrf-token"]').content;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showHistoryAlert(message, type = "success") {
  document.getElementById("historyAlert").innerHTML = `
    <div class="alert alert-${type} alert-dismissible fade show" role="alert">
      ${escapeHtml(message)}
      <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    </div>`;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(),
      ...(options.headers || {}),
    },
  });
  const payload = await response.json();
  if (!response.ok || !payload.ok) {
    throw new Error(payload.message || "Request failed");
  }
  return payload;
}

function actionButtons(row) {
  const download = row.download_url
    ? `<a class="btn btn-sm btn-outline-primary btn-icon" href="${row.download_url}" title="Download" aria-label="Download" data-bs-toggle="tooltip"><i class="bi bi-download"></i></a>`
    : `<button class="btn btn-sm btn-outline-secondary btn-icon" type="button" disabled title="No file" aria-label="No file" data-bs-toggle="tooltip"><i class="bi bi-file-earmark-x"></i></button>`;
  return `
    <div class="btn-group btn-group-sm" role="group">
      ${download}
      <button class="btn btn-outline-secondary btn-icon" type="button" data-action="rename" data-id="${row.id}" data-filename="${escapeHtml(row.filename)}" title="Edit filename" aria-label="Edit filename" data-bs-toggle="tooltip"><i class="bi bi-pencil-square"></i></button>
      <button class="btn btn-outline-warning btn-icon" type="button" data-action="delete-file" data-id="${row.id}" title="Delete file" aria-label="Delete file" data-bs-toggle="tooltip"><i class="bi bi-file-earmark-x"></i></button>
      <button class="btn btn-outline-danger btn-icon" type="button" data-action="delete-log" data-id="${row.id}" title="Delete import" aria-label="Delete import" data-bs-toggle="tooltip"><i class="bi bi-trash"></i></button>
    </div>`;
}

function renderGenericTable(headId, bodyId, columns, rows) {
  const visibleColumns = columns.filter((col) => col !== "stored_filename");
  document.getElementById(headId).innerHTML =
    visibleColumns.map((col) => `<th>${escapeHtml(col)}</th>`).join("") + '<th class="text-end">Actions</th>';

  document.getElementById(bodyId).innerHTML = rows.length
    ? rows.map((row) => {
        const cells = visibleColumns.map((col) => `<td>${escapeHtml(row[col])}</td>`).join("");
        return `<tr>${cells}<td class="text-end text-nowrap">${actionButtons(row)}</td></tr>`;
      }).join("")
    : `<tr><td colspan="${Math.max(visibleColumns.length + 1, 1)}" class="text-center text-secondary py-4">No data</td></tr>`;
  document.querySelectorAll('#historyBody [title]').forEach((element) => {
    if (window.bootstrap) new bootstrap.Tooltip(element);
  });
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

async function handleHistoryAction(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) return;

  const id = button.dataset.id;
  const action = button.dataset.action;
  try {
    let payload;
    if (action === "rename") {
      const nextName = window.prompt("New display filename", button.dataset.filename || "");
      if (!nextName) return;
      payload = await requestJson(`/api/upload-logs/${id}`, {
        method: "POST",
        body: JSON.stringify({ filename: nextName }),
      });
    } else if (action === "delete-file") {
      if (!window.confirm("Delete only the stored Excel file from server? Imported dashboard data will remain. Use Delete import to remove dashboard data.")) return;
      payload = await requestJson(`/api/upload-logs/${id}/file`, { method: "DELETE" });
    } else if (action === "delete-log") {
      if (!window.confirm("Delete this upload history, stored Excel file, and imported rows for this file?")) return;
      payload = await requestJson(`/api/upload-logs/${id}`, { method: "DELETE" });
    }
    showHistoryAlert(payload.message);
    await loadHistory();
  } catch (error) {
    showHistoryAlert(error.message || "Action failed", "danger");
  }
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
  document.getElementById("historyBody").addEventListener("click", handleHistoryAction);
  loadHistory();
});
