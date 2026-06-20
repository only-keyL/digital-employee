/**
 * 运营看板 ECharts 图表初始化
 * 数据来源：Jinja 模板注入的 opChartData（后端 OperationDashboardService 已计算，本文件仅负责展示）
 */

(function () {
  "use strict";

  const charts = [];

  function isAllZero(values) {
    return !values || values.every((v) => !v || v === 0);
  }

  function showEmptyHint(container, message) {
    if (!container) return;
    container.innerHTML =
      '<div class="dashboard-empty-hint">' + (message || "暂无数据") + "</div>";
  }

  // 中文注释：初始化置信度分布柱状图，展示回答可信程度
  function initConfidenceBar(data) {
    const el = document.getElementById("chart-confidence-bar");
    if (!el || typeof echarts === "undefined") return;

    const c = data.confidence || {};
    const values = [c.high || 0, c.medium || 0, c.low || 0, c.none || 0];
    if (isAllZero(values)) {
      showEmptyHint(el, "暂无置信度分布数据");
      return;
    }

    const chart = echarts.init(el);
    chart.setOption({
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: "3%", right: "4%", bottom: "6%", top: "12%", containLabel: true },
      xAxis: {
        type: "category",
        data: ["高", "中", "低", "无"],
        axisLabel: { color: "#64748b" },
      },
      yAxis: { type: "value", name: "次数", axisLabel: { color: "#64748b" } },
      series: [
        {
          name: "置信度",
          type: "bar",
          data: values,
          barMaxWidth: 48,
          itemStyle: {
            color: function (params) {
              const colors = ["#22c55e", "#3b82f6", "#f59e0b", "#94a3b8"];
              return colors[params.dataIndex] || "#3b82f6";
            },
            borderRadius: [4, 4, 0, 0],
          },
        },
      ],
    });
    charts.push(chart);
  }

  // 中文注释：初始化反馈分布饼图，展示用户反馈质量
  function initFeedbackPie(data) {
    const el = document.getElementById("chart-feedback-pie");
    if (!el || typeof echarts === "undefined") return;

    const f = data.feedback || {};
    const useful = f.useful || 0;
    const useless = f.useless || 0;
    const supplement = f.supplement || 0;
    if (isAllZero([useful, useless, supplement])) {
      showEmptyHint(el, "暂无反馈分布数据");
      return;
    }

    const chart = echarts.init(el);
    chart.setOption({
      tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
      legend: { bottom: 0, textStyle: { color: "#64748b" } },
      color: ["#22c55e", "#ef4444", "#8b5cf6"],
      series: [
        {
          name: "反馈分布",
          type: "pie",
          radius: "62%",
          center: ["50%", "45%"],
          itemStyle: { borderRadius: 6, borderColor: "#fff", borderWidth: 2 },
          label: { formatter: "{b}\n{c}" },
          data: [
            { value: useful, name: "有用" },
            { value: useless, name: "无用" },
            { value: supplement, name: "补充" },
          ],
        },
      ],
    });
    charts.push(chart);
  }

  // 中文注释：初始化知识状态分布柱状图，展示知识治理进度
  function initKnowledgeBar(data) {
    const el = document.getElementById("chart-knowledge-bar");
    if (!el || typeof echarts === "undefined") return;

    const k = data.knowledge || {};
    const values = [
      k.approved || 0,
      k.pending || 0,
      k.draft || 0,
      k.rejected || 0,
      k.enabled || 0,
    ];
    if (isAllZero(values)) {
      showEmptyHint(el, "暂无知识状态数据");
      return;
    }

    const chart = echarts.init(el);
    chart.setOption({
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: "3%", right: "4%", bottom: "6%", top: "12%", containLabel: true },
      xAxis: {
        type: "category",
        data: ["已审核", "待审核", "草稿", "已拒绝", "启用中"],
        axisLabel: { rotate: 20, fontSize: 10, color: "#64748b" },
      },
      yAxis: { type: "value", name: "数量", axisLabel: { color: "#64748b" } },
      series: [
        {
          name: "知识状态",
          type: "bar",
          data: values,
          barMaxWidth: 40,
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "#6366f1" },
              { offset: 1, color: "#a5b4fc" },
            ]),
            borderRadius: [4, 4, 0, 0],
          },
        },
      ],
    });
    charts.push(chart);
  }

  // 中文注释：初始化重复检测分布环形图，展示知识库治理风险
  function initDuplicateRing(data) {
    const el = document.getElementById("chart-duplicate-ring");
    if (!el || typeof echarts === "undefined") return;

    const d = data.duplicate || {};
    const high = d.high_duplicate || 0;
    const suspected = d.suspected_duplicate || 0;
    const related = d.related || 0;
    const none = d.none || 0;
    if (isAllZero([high, suspected, related, none])) {
      showEmptyHint(el, "暂无重复检测数据");
      return;
    }

    const chart = echarts.init(el);
    chart.setOption({
      tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
      legend: { bottom: 0, textStyle: { color: "#64748b", fontSize: 11 } },
      color: ["#ef4444", "#f59e0b", "#3b82f6", "#22c55e"],
      series: [
        {
          name: "重复检测",
          type: "pie",
          radius: ["40%", "66%"],
          center: ["50%", "42%"],
          itemStyle: { borderRadius: 6, borderColor: "#fff", borderWidth: 2 },
          label: { formatter: "{b}\n{c}", fontSize: 11 },
          data: [
            { value: high, name: "高度重复" },
            { value: suspected, name: "疑似重复" },
            { value: related, name: "相关知识" },
            { value: none, name: "无明显重复" },
          ],
        },
      ],
    });
    charts.push(chart);
  }

  // 中文注释：初始化高频系统/模块 Top10 横向柱状图，展示问题集中业务域
  function initTopModulesBar(data) {
    const el = document.getElementById("chart-top-modules");
    if (!el || typeof echarts === "undefined") return;

    const items = data.topModules || [];
    if (!items.length) {
      showEmptyHint(el, "暂无系统/模块 Top 数据");
      return;
    }

    const labels = items.map(function (item) {
      const sys = item.system_name || "未知系统";
      const mod = item.module_name || "未知模块";
      const text = sys + " / " + mod;
      return text.length > 22 ? text.slice(0, 22) + "…" : text;
    });
    const values = items.map(function (item) {
      return item.ask_count || 0;
    });

    const chart = echarts.init(el);
    chart.setOption({
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter: function (params) {
          const idx = params[0].dataIndex;
          const raw = items[idx];
          return (
            (raw.system_name || "") +
            " / " +
            (raw.module_name || "") +
            "<br/>提问数: " +
            (raw.ask_count || 0)
          );
        },
      },
      grid: { left: "3%", right: "8%", bottom: "4%", top: "4%", containLabel: true },
      xAxis: { type: "value", name: "提问数", axisLabel: { color: "#64748b" } },
      yAxis: {
        type: "category",
        data: labels.slice().reverse(),
        axisLabel: { fontSize: 10, color: "#64748b" },
      },
      series: [
        {
          name: "提问数",
          type: "bar",
          data: values.slice().reverse(),
          barMaxWidth: 22,
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
              { offset: 0, color: "#3b82f6" },
              { offset: 1, color: "#60a5fa" },
            ]),
            borderRadius: [0, 4, 4, 0],
          },
        },
      ],
    });
    charts.push(chart);
  }

  // 中文注释：窗口尺寸变化时自动重绘图表，避免页面缩放后图表变形
  function bindResize() {
    window.addEventListener("resize", function () {
      charts.forEach(function (chart) {
        if (chart && !chart.isDisposed()) {
          chart.resize();
        }
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (typeof opChartData === "undefined") return;
    initConfidenceBar(opChartData);
    initFeedbackPie(opChartData);
    initKnowledgeBar(opChartData);
    initDuplicateRing(opChartData);
    initTopModulesBar(opChartData);
    bindResize();
  });
})();
