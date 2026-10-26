(() => {
  "use strict";

  const qs = (selector, root = document) => root.querySelector(selector);
  const qsa = (selector, root = document) => [...root.querySelectorAll(selector)];

  async function loadJson(path) {
    const response = await fetch(path);
    if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
    return response.json();
  }

  function renderKpis(reproduction) {
    Object.entries(reproduction.totals).forEach(([key, value]) => {
      const target = qs(`[data-kpi="${key}"]`);
      if (target) target.textContent = value.toLocaleString("zh-CN");
    });
  }

  function renderResults(paper) {
    const chart = qs("#result-chart");
    if (!chart) return;
    chart.innerHTML = paper.main_results.map((row) => `
      <div class="chart-row ${row.key === "average" ? "task-average" : ""}">
        <span class="chart-task">${row.task}</span>
        <div class="bars">
          <div class="bar visual-motion" tabindex="0" aria-label="${row.task} 视觉动作示范 ${row.visual_motion}%"><i style="width:${row.visual_motion * 2.5}%"></i></div>
          <div class="bar tactile-eta" tabindex="0" aria-label="${row.task} Tactile-ETA ${row.tactile_eta}%"><i style="width:${row.tactile_eta * 2.5}%"></i></div>
        </div>
        <span class="chart-value">${row.tactile_eta}%</span>
      </div>`).join("");

    const ablation = qs("#ablation-chart");
    ablation.innerHTML = paper.representation_ablation.map((row) => `
      <div class="ablation-row ${row.success === 36 ? "best" : ""}">
        <span>${row.name}</span><i><b style="width:${row.success * 2.5}%"></b></i><strong>${row.success}%</strong>
      </div>`).join("");

    const trials = qs("#robot-trials");
    trials.innerHTML = paper.real_robot.map((row) => `
      <div class="robot-row"><div><strong>${row.task}</strong><span>${row.with_demo}/${row.trials}</span></div>
        <div class="trial-line"><span>无示范</span>${Array.from({ length: row.trials }, () => '<i class="trial-dot"></i>').join("")}</div>
        <div class="trial-line"><span>1 条示范</span>${Array.from({ length: row.trials }, (_, index) => `<i class="trial-dot ${index < row.with_demo ? "success" : ""}"></i>`).join("")}</div>
      </div>`).join("");

    const models = qs("#model-chart");
    models.innerHTML = paper.model_comparison.map((row) => `
      <div class="model-row ${row.success === 36 ? "best" : ""}">
        <span>${row.model}</span><i><b style="width:${row.success * 2.5}%"></b></i><strong>${row.success}%</strong>
      </div>`).join("");
  }

  function setupMemoryViewer(reproduction) {
    const media = reproduction.representative_media.insert_tube;
    const left = media["e0_s4_left_tactile.png"].frames;
    const right = media["e0_s4_right_tactile.png"].frames;
    const labels = ["动作起点", "最大变化前", "最大变化后", "动作终点"];
    const leftImage = qs("#left-frame");
    const rightImage = qs("#right-frame");
    const frameLabel = qs("#frame-label");
    const maxDifference = Math.max(...left.map((row) => row.display_mean_abs_rgb_difference_from_first), ...right.map((row) => row.display_mean_abs_rgb_difference_from_first));

    function selectFrame(index) {
      const l = left[index];
      const r = right[index];
      leftImage.src = l.path;
      rightImage.src = r.path;
      leftImage.alt = `左侧触觉${labels[index]}，记录步 ${l.recorded_step}`;
      rightImage.alt = `右侧触觉${labels[index]}，记录步 ${r.recorded_step}`;
      frameLabel.textContent = `${labels[index]} · step ${l.recorded_step}`;
      qs("#left-diff").textContent = `Δ ${l.display_mean_abs_rgb_difference_from_first.toFixed(2)}`;
      qs("#right-diff").textContent = `Δ ${r.display_mean_abs_rgb_difference_from_first.toFixed(2)}`;
      qs("#left-diff-bar").style.width = `${l.display_mean_abs_rgb_difference_from_first / maxDifference * 100}%`;
      qs("#right-diff-bar").style.width = `${r.display_mean_abs_rgb_difference_from_first / maxDifference * 100}%`;
      qsa(".frame-button").forEach((button) => button.classList.toggle("active", Number(button.dataset.frame) === index));
    }

    qsa(".frame-button").forEach((button) => button.addEventListener("click", () => selectFrame(Number(button.dataset.frame))));
    selectFrame(0);
  }

  function setupActiveNavigation() {
    const links = qsa(".site-header nav a");
    const sections = links.map((link) => qs(link.getAttribute("href"))).filter(Boolean);
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        links.forEach((link) => link.toggleAttribute("aria-current", link.getAttribute("href") === `#${entry.target.id}`));
      });
    }, { rootMargin: "-30% 0px -60%", threshold: 0 });
    sections.forEach((section) => observer.observe(section));
  }

  async function start() {
    try {
      const [reproduction, paper] = await Promise.all([
        loadJson("data/reproduction-summary.json"),
        loadJson("data/paper-results.json"),
      ]);
      renderKpis(reproduction);
      renderResults(paper);
      setupMemoryViewer(reproduction);
      setupActiveNavigation();
      document.documentElement.dataset.ready = "true";
    } catch (error) {
      console.error(error);
      document.documentElement.dataset.ready = "error";
    }
  }

  start();
})();
