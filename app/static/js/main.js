document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const message = form.getAttribute("data-confirm") || "确认执行该操作？";
      if (!window.confirm(message)) {
        event.preventDefault();
      }
    });
  });
});
