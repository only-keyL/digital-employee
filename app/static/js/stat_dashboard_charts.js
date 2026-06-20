/**
 * 统计看板 ECharts 图表初始化
 * 数据来源：Jinja 模板注入的 statChartData（后端 StatisticsService 已计算，本文件仅负责展示）
 */

(function () {
  "use strict";

  const charts = [];

  // 中文注释：判断数值总和是否为零，用于空数据兜底
  function isAllZero(values) {
    return !values || values.every((v) => !v || v === 0);
  }

  // 中文注释：在图表容器上显示友好空数据提示
  function showEmptyHint(container, message) {
    if (!container) return;
    container.innerHTML =
      '<div class="dashboard-empty-hint">' + (message || "暂无数据") + "</div>";
  }

  // 中文注释：初始化问答命中分布饼图，展示知识库覆盖效果（命中 vs 未命中）
  function initHitDistributionChart(data) {
    const el = document.getElementById("chart-hit-distribution");
    if (!el || typeof echarts === "undefined") return;

    const matched = data.matched || 0;
    const missed = data.missed || 0;
    if (isAllZero([matched, missed])) {
      showEmptyHint(el, "暂无问答命中数据");
      return;
    }

    const chart = echarts.init(el);
    chart.setOption({
      tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
      legend: { bottom: 0, textStyle: { color: "#64748b" } },
      color: ["#3b82f6", "#f59e0b"],
      series: [
        {
          name: "问答命中分布",
          type: "pie",
          radius: ["40%", "68%"],
          center: ["50%", "45%"],
          itemStyle: { borderRadius: 6, borderColor: "#fff", borderWidth: 2 },
          label: { formatter: "{b}\n{c}" },
          data: [
            { value: matched, name: "命中" },
            { value: missed, name: "未命中" },
          ],
        },
      ],
    });
    charts.push(chart);
  }

  // 中文注释：初始化反馈结果环形图，展示回答质量反馈结构
  function initFeedbackRingChart(data) {
    const el = document.getElementById("chart-feedback-ring");
    if (!el || typeof echarts === "undefined") return;

    const useful = data.useful || 0;
    const useless = data.useless || 0;
    const needHuman = data.needHuman || 0;
    if (isAllZero([useful, useless, needHuman])) {
      showEmptyHint(el, "暂无反馈数据");
      return;
    }

    const chart = echarts.init(el);
    chart.setOption({
      tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
      legend: { bottom: 0, textStyle: { color: "#64748b" } },
      color: ["#22c55e", "#ef4444", "#a855f7"],
      series: [
        {
          name: "反馈分布",
          type: "pie",
          radius: ["42%", "68%"],
          center: ["50%", "45%"],
          itemStyle: { borderRadius: 6, borderColor: "#fff", borderWidth: 2 },
          label: { formatter: "{b}\n{c}" },
          data: [
            { value: useful, name: "有用反馈" },
            { value: useless, name: "无用反馈" },
            { value: needHuman, name: "需人工反馈" },
          ],
        },
      ],
    });
    charts.push(chart);
  }

  // 中文注释：初始化命中率仪表盘，让领导一眼看到问答效果
  function initMatchRateGauge(data) {
    const el = document.getElementById("chart-match-rate-gauge");
    if (!el || typeof echarts === "undefined") return;

    const rate = Math.round((data.matchRate || 0) * 1000) / 10;

    const chart = echarts.init(el);
    chart.setOption({
      series: [
        {
          type: "gauge",
          startAngle: 200,
          endAngle: -20,
          min: 0,
          max: 100,
          splitNumber: 5,
          radius: "85%",
          center: ["50%", "58%"],
          axisLine: {
            lineStyle: {
              width: 14,
              color: [
                [0.5, "#f59e0b"],
                [0.8, "#3b82f6"],
                [1, "#22c55e"],
              ],
            },
          },
          pointer: { itemStyle: { color: "#1e293b" } },
          axisTick: { distance: -14, length: 6 },
          splitLine: { distance: -14, length: 12 },
          axisLabel: { color: "#64748b", distance: 20, fontSize: 11 },
          detail: {
            valueAnimation: true,
            formatter: "{value}%",
            color: "#1e293b",
            fontSize: 28,
            fontWeight: 700,
            offsetCenter: [0, "20%"],
          },
          title: {
            offsetCenter: [0, "45%"],
            fontSize: 13,
            color: "#64748b",
          },
          data: [{ value: rate, name: "命中率" }],
        },
      ],
    });
    charts.push(chart);
  }

  // 中文注释：初始化 Top 未命中问题柱状图，展示知识库补齐重点
  function initTopUnansweredBar(data) {
    const el = document.getElementById("chart-top-unanswered");
    if (!el || typeof echarts === "undefined") return;

    const items = data.topUnanswered || [];
    if (!items.length) {
      showEmptyHint(el, "暂无未命中 Top 数据");
      return;
    }

    const labels = items.map((item) => {
      const text = item.summary || item.question || "未知";
      return text.length > 18 ? text.slice(0, 18) + "…" : text;
    });
    const values = items.map((item) => item.frequency || 0);

    const chart = echarts.init(el);
    chart.setOption({
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter: function (params) {
          const idx = params[0].dataIndex;
          const raw = items[idx];
          const full = (raw && (raw.summary || raw.question)) || "";
          return full + "<br/>频次: " + (raw.frequency || 0);
        },
      },
      grid: { left: "3%", right: "4%", bottom: "8%", top: "8%", containLabel: true },
      xAxis: {
        type: "category",
        data: labels,
        axisLabel: { rotate: 30, fontSize: 10, color: "#64748b" },
      },
      yAxis: { type: "value", name: "频次", axisLabel: { color: "#64748b" } },
      series: [
        {
          name: "未命中频次",
          type: "bar",
          data: values,
          barMaxWidth: 36,
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "#f59e0b" },
              { offset: 1, color: "#fbbf24" },
            ]),
            borderRadius: [4, 4, 0, 0],
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
    if (typeof statChartData === "undefined") return;
    initHitDistributionChart(statChartData);
    initFeedbackRingChart(statChartData);
    initMatchRateGauge(statChartData);
    initTopUnansweredBar(statChartData);
    bindResize();
  });
})();
