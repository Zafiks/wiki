// Поле поиска над таблицами (страница «Предметы по названию» и команды):
// прячет строки без совпадения и целые блоки, где ничего не осталось.
function nwSetupFilter() {
  const input = document.querySelector(".nw-filter");
  if (!input || input.dataset.ready) return;
  input.dataset.ready = "1";
  const empty = document.querySelector(".nw-filter-empty");
  const scope = input.closest("article") || document;
  const norm = (s) => s.toLowerCase().replace(/ё/g, "е");

  input.addEventListener("input", () => {
    const q = norm(input.value.trim());
    let shown = 0;
    scope.querySelectorAll("table").forEach((table) => {
      let left = 0;
      table.querySelectorAll("tbody tr").forEach((tr) => {
        const hit = !q || norm(tr.textContent).includes(q);
        tr.hidden = !hit;
        if (hit) left++;
      });
      shown += left;
      const group = table.closest(".nw-rename-group, .nw-filter-group");
      if (group) group.hidden = left === 0;
    });
    // заголовки разделов (h2) без видимых блоков — тоже прячем
    scope.querySelectorAll("h2").forEach((h2) => {
      let el = h2.nextElementSibling, any = false, groups = 0;
      while (el && el.tagName !== "H2") {
        if (el.matches(".nw-rename-group, .nw-filter-group")) { groups++; if (!el.hidden) any = true; }
        el = el.nextElementSibling;
      }
      if (groups) h2.hidden = !any;
    });
    if (empty) empty.hidden = shown > 0 || !q;
  });
}

if (typeof document$ !== "undefined") {
  document$.subscribe(nwSetupFilter); // мгновенная навигация Material
} else {
  document.addEventListener("DOMContentLoaded", nwSetupFilter);
}
