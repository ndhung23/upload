(function () {
  const button = document.getElementById("themeToggle");
  const saved = localStorage.getItem("dashboard-theme");

  function setTheme(mode) {
    document.body.classList.toggle("dark-mode", mode === "dark");
    document.documentElement.setAttribute("data-bs-theme", mode);
    localStorage.setItem("dashboard-theme", mode);
    if (button) button.textContent = mode === "dark" ? "Light mode" : "Dark mode";
  }

  setTheme(saved || "light");

  if (button) {
    button.addEventListener("click", function () {
      const next = document.body.classList.contains("dark-mode") ? "light" : "dark";
      setTheme(next);
      window.dispatchEvent(new Event("resize"));
    });
  }

  document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (element) {
    new bootstrap.Tooltip(element);
  });

  const sidebarToggle = document.getElementById("sidebarToggle");
  const shell = document.querySelector(".app-shell");
  const sidebarState = localStorage.getItem("sidebar-collapsed") === "1";
  if (shell) shell.classList.toggle("sidebar-collapsed", sidebarState);
  if (sidebarToggle && shell) {
    sidebarToggle.addEventListener("click", function () {
      const collapsed = !shell.classList.contains("sidebar-collapsed");
      shell.classList.toggle("sidebar-collapsed", collapsed);
      localStorage.setItem("sidebar-collapsed", collapsed ? "1" : "0");
      window.dispatchEvent(new Event("resize"));
    });
  }
})();
