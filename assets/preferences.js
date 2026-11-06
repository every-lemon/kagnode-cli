// Apply saved appearance before the first paint. Storage may be unavailable.
(() => {
  try {
    document.documentElement.dataset.theme =
      localStorage.getItem("kagnode.theme") === "light" ? "light" : "dark";
    document.documentElement.classList.toggle(
      "collapsed",
      localStorage.getItem("kagnode.collapsed") === "true",
    );
  } catch {}
})();
