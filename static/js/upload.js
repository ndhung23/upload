document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("uploadForm");
  const result = document.getElementById("uploadResult");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button[type='submit']");
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = "Processing...";
    result.innerHTML = "";

    try {
      const response = await fetch("/api/upload", {
        method: "POST",
        body: new FormData(form),
        headers: {
          "X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content,
        },
      });
      const data = await response.json();
      const type = data.ok ? "success" : "danger";
      result.innerHTML = `<div class="alert alert-${type}">${data.message}</div>`;
      if (data.ok) {
        form.reset();
        const summary = data.result || {};
        const labels = [
          ["total_rows", "Total rows"],
          ["inserted", "Inserted"],
          ["updated", "Updated"],
          ["skipped", "Skipped"],
          ["invalid_rows", "Invalid rows"],
          ["header_row", "Detected header row"],
        ];
        document.getElementById("uploadSummaryList").innerHTML = labels
          .map(([key, label]) => `<dt class="col-6">${label}</dt><dd class="col-6">${summary[key] ?? 0}</dd>`)
          .join("");
        new bootstrap.Modal(document.getElementById("uploadSummaryModal")).show();
      }
    } catch (error) {
      result.innerHTML = `<div class="alert alert-danger">${error.message || "Upload failed"}</div>`;
    } finally {
      button.disabled = false;
      button.textContent = originalText;
    }
  });
});
