const themeKey = document.body.dataset.themeKey || "orbit-usecase-theme";
const applyTheme = (theme) => {
  document.documentElement.dataset.theme = theme;
  document.querySelector("#guide-theme").textContent = theme === "dark" ? "Light theme" : "Dark theme";
  localStorage.setItem(themeKey, theme);
};
const saved = localStorage.getItem(themeKey);
const preferred = matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
applyTheme(saved === "light" || saved === "dark" ? saved : preferred);
document.querySelector("#guide-theme").addEventListener("click", () => {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});

