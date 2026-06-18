/**
 * 问答测试页脚本。
 * 调用 /api/ask 展示命中结果，并支持提交 useful/useless/need_human 反馈。
 */
document.addEventListener("DOMContentLoaded", () => {
  const askForm = document.getElementById("ask-form");
  if (!askForm) {
    return;
  }

  const resultBox = document.getElementById("ask-result");
  const errorBox = document.getElementById("ask-error");
  const submitBtn = document.getElementById("ask-submit");
  const feedbackBox = document.getElementById("feedback-panel");
  const feedbackMessage = document.getElementById("feedback-message");
  const feedbackButtons = Array.from(document.querySelectorAll("[data-feedback-type]"));

  /** @type {number|null} 最近一次问答的 question_log_id */
  let lastQuestionLogId = null;

  /**
   * 启用或禁用反馈按钮。
   * @param {boolean} enabled
   */
  function setFeedbackEnabled(enabled) {
    feedbackButtons.forEach((button) => {
      button.disabled = !enabled;
    });
  }

  /** 重置反馈面板状态（无 log_id 时禁用提交）。 */
  function resetFeedbackState() {
    lastQuestionLogId = null;
    setFeedbackEnabled(false);
    if (feedbackMessage) {
      feedbackMessage.classList.add("d-none");
      feedbackMessage.textContent = "";
      feedbackMessage.className = "alert mt-2 d-none";
    }
  }

  /**
   * 在反馈区域展示提示消息。
   * @param {string} text
   * @param {string} type Bootstrap alert 类型，如 success、danger
   */
  function showFeedbackMessage(text, type) {
    if (!feedbackMessage) return;
    feedbackMessage.textContent = text;
    feedbackMessage.className = `alert mt-2 alert-${type || "info"}`;
    feedbackMessage.classList.remove("d-none");
  }

  /**
   * 向 /api/feedback 提交用户反馈。
   * @param {string} feedbackType useful | useless | need_human
   */
  async function submitFeedback(feedbackType) {
    if (!lastQuestionLogId) {
      showFeedbackMessage("当前回答没有 question_log_id，无法提交反馈。", "warning");
      return;
    }

    const userId = (document.getElementById("user_id")?.value || "").trim() || "anonymous";
    try {
      const response = await fetch("/api/feedback/legacy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question_log_id: lastQuestionLogId,
          feedback_type: feedbackType,
          user_id: userId,
        }),
      });
      const data = await response.json();
      if (!data.success) {
        showFeedbackMessage(data.message || "反馈提交失败", "danger");
        return;
      }
      setFeedbackEnabled(false);
      showFeedbackMessage("反馈已提交", "success");
    } catch (error) {
      showFeedbackMessage(`反馈提交失败：${error}`, "danger");
    }
  }

  feedbackButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const feedbackType = button.getAttribute("data-feedback-type");
      if (!feedbackType || button.disabled) {
        return;
      }
      await submitFeedback(feedbackType);
    });
  });

  askForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorBox.classList.add("d-none");
    resultBox.classList.add("d-none");
    resetFeedbackState();
    submitBtn.disabled = true;

    const question = document.getElementById("question").value.trim();
    const userId = document.getElementById("user_id").value.trim();
    const groupId = document.getElementById("group_id").value.trim();

    const payload = {
      question,
      source_type: "web",
    };
    if (userId) payload.user_id = userId;
    if (groupId) payload.group_id = groupId;

    try {
      const response = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();

      document.getElementById("result-matched").textContent = data.matched ? "是" : "否";
      document.getElementById("result-score").textContent = String(data.similarity_score);
      document.getElementById("result-log-id").textContent =
        data.question_log_id === null ? "-" : String(data.question_log_id);
      document.getElementById("result-fallback").textContent = data.fallback_reason || "-";
      document.getElementById("result-answer").textContent = data.answer || "";

      if (data.sources && data.sources.length > 0) {
        document.getElementById("result-sources").textContent = data.sources
          .map((item) => `${item.title}（card_id=${item.card_id}, score=${item.score}）`)
          .join("；");
      } else {
        document.getElementById("result-sources").textContent = "-";
      }

      resultBox.classList.remove("d-none");
      if (feedbackBox) {
        feedbackBox.classList.remove("d-none");
      }

      if (data.question_log_id !== null && data.question_log_id !== undefined) {
        lastQuestionLogId = data.question_log_id;
        setFeedbackEnabled(true);
      } else {
        resetFeedbackState();
      }

      if (data.fallback_reason === "问题不能为空") {
        errorBox.textContent = data.fallback_reason;
        errorBox.classList.remove("d-none");
      }
    } catch (error) {
      errorBox.textContent = `请求失败：${error}`;
      errorBox.classList.remove("d-none");
    } finally {
      submitBtn.disabled = false;
    }
  });
});
