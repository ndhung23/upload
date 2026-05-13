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
})();
