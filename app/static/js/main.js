/**
 * 全站通用前端脚本。
 * 为带 data-confirm 属性的表单绑定提交前二次确认。
 */
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
