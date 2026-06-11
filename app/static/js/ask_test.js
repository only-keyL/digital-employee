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

  let lastQuestionLogId = null;

  function setFeedbackEnabled(enabled) {
    feedbackButtons.forEach((button) => {
      button.disabled = !enabled;
    });
  }

  function resetFeedbackState() {
    lastQuestionLogId = null;
    setFeedbackEnabled(false);
    if (feedbackMessage) {
      feedbackMessage.classList.add("d-none");
      feedbackMessage.textContent = "";
      feedbackMessage.className = "alert mt-2 d-none";
    }
  }

  function showFeedbackMessage(text, type) {
    if (!feedbackMessage) return;
    feedbackMessage.textContent = text;
    feedbackMessage.className = `alert mt-2 alert-${type || "info"}`;
    feedbackMessage.classList.remove("d-none");
  }

  async function submitFeedback(feedbackType) {
    if (!lastQuestionLogId) {
      showFeedbackMessage("当前回答没有 question_log_id，无法提交反馈。", "warning");
      return;
    }

    const userId = (document.getElementById("user_id")?.value || "").trim() || "anonymous";
    try {
      const response = await fetch("/api/feedback", {
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
