(function () {
    const config = window.UNANSWERED_DETAIL || {};
    const unansweredId = config.id;
    const status = config.status;

    if (!unansweredId || status !== "pending") {
        return;
    }

    const messageEl = document.getElementById("draft-message");
    const form = document.getElementById("convert-form");
    const btnGenerate = document.getElementById("btn-generate-draft");
    const btnIgnore = document.getElementById("btn-ignore");

    function showMessage(text, type) {
        if (!messageEl) return;
        messageEl.textContent = text;
        messageEl.className = "alert mt-3 alert-" + (type || "info");
        messageEl.classList.remove("d-none");
    }

    function fillDraftForm(data) {
        const setValue = (id, value) => {
            const el = document.getElementById(id);
            if (el && value !== undefined && value !== null) {
                el.value = value;
            }
        };
        setValue("draft-title", data.title);
        setValue("draft-question", data.question);
        setValue("draft-answer", data.answer);
        setValue("draft-system", data.system_name);
        setValue("draft-module", data.module_name);
        setValue("draft-tags", data.tags);
        setValue("draft-troubleshooting", data.troubleshooting_steps);
        setValue("draft-solution", data.solution);
        setValue("draft-risk", data.risk_notice);
    }

    function collectPayload() {
        const answer = (document.getElementById("draft-answer")?.value || "").trim();
        if (!answer) {
            throw new Error("标准答案不能为空");
        }
        return {
            title: (document.getElementById("draft-title")?.value || "").trim(),
            question: (document.getElementById("draft-question")?.value || "").trim(),
            answer: answer,
            system_name: document.getElementById("draft-system")?.value || "",
            module_name: document.getElementById("draft-module")?.value || "",
            tags: document.getElementById("draft-tags")?.value || "",
            troubleshooting_steps: document.getElementById("draft-troubleshooting")?.value || "",
            solution: document.getElementById("draft-solution")?.value || "",
            risk_notice: document.getElementById("draft-risk")?.value || "",
            source_group: "未命中沉淀",
            source_user: "admin",
        };
    }

    async function requestJson(url, options) {
        const resp = await fetch(url, options);
        const data = await resp.json();
        if (!resp.ok || !data.success) {
            throw new Error(data.message || "请求失败");
        }
        return data;
    }

    if (btnGenerate) {
        btnGenerate.addEventListener("click", async function () {
            btnGenerate.disabled = true;
            showMessage("正在生成草稿预览...", "info");
            try {
                const result = await requestJson(
                    "/api/unanswered-questions/" + unansweredId + "/generate-draft",
                    { method: "POST", headers: { "Content-Type": "application/json" } }
                );
                fillDraftForm(result.data || {});
                showMessage("草稿预览已填充，请人工校对后确认转换。", "success");
            } catch (err) {
                showMessage(err.message || "生成草稿失败", "danger");
            } finally {
                btnGenerate.disabled = false;
            }
        });
    }

    if (form) {
        form.addEventListener("submit", async function (event) {
            event.preventDefault();
            try {
                const payload = collectPayload();
                if (!payload.title || !payload.question) {
                    throw new Error("标题和标准问题不能为空");
                }
                const result = await requestJson(
                    "/api/unanswered-questions/" + unansweredId + "/convert",
                    {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(payload),
                    }
                );
                const cardId = result.data?.convert_card_id || result.data?.knowledge_card_id;
                showMessage("已转为知识卡片 draft，正在跳转...", "success");
                if (cardId) {
                    window.location.href = "/knowledge-cards/" + cardId;
                } else {
                    window.location.reload();
                }
            } catch (err) {
                showMessage(err.message || "转换失败", "danger");
            }
        });
    }

    if (btnIgnore) {
        btnIgnore.addEventListener("click", async function () {
            if (!window.confirm("确认忽略该未命中问题？忽略后为终态。")) {
                return;
            }
            try {
                await requestJson(
                    "/api/unanswered-questions/" + unansweredId + "/ignore",
                    { method: "POST", headers: { "Content-Type": "application/json" } }
                );
                window.location.reload();
            } catch (err) {
                showMessage(err.message || "忽略失败", "danger");
            }
        });
    }
})();
