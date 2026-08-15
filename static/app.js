document.querySelectorAll("#report th").forEach((header, index) => {
  header.tabIndex = 0;
  header.setAttribute("role", "button");
  const sort = () => {
    const body = header.closest("table").querySelector("tbody");
    const rows = [...body.querySelectorAll("tr")].filter(row => row.children.length > 1);
    const ascending = header.dataset.direction !== "asc";
    header.closest("tr").querySelectorAll("th").forEach(th => th.classList.remove("active-sort"));
    header.classList.add("active-sort");
    header.dataset.direction = ascending ? "asc" : "desc";
    rows.sort((a, b) => {
      const av = a.children[index].dataset.sort ?? a.children[index].textContent.trim();
      const bv = b.children[index].dataset.sort ?? b.children[index].textContent.trim();
      const result = header.dataset.type === "number" ? Number(av) - Number(bv) : av.localeCompare(bv);
      return ascending ? result : -result;
    });
    rows.forEach(row => body.appendChild(row));
  };
  header.addEventListener("click", sort);
  header.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") sort(); });
});

const queryForm = document.querySelector("#query-form");
const queryOverlay = document.querySelector("#query-overlay");
if (queryForm && queryOverlay) {
  queryForm.addEventListener("submit", () => {
    queryOverlay.classList.add("visible");
    queryOverlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("query-running");
    const submitButton = queryForm.querySelector("button[type='submit']");
    if (submitButton) submitButton.disabled = true;
  });
}
