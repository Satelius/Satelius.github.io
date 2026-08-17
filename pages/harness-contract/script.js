const stageData = {
  0: {
    kicker: "STAGE 0 · BOUNDED INPUT",
    title: "系统先决定哪些话可以被理解。",
    body: "受限解析器只接受桌面物体、颜色、材质、区域和少量空间关系。路径、资产编号、坐标、四元数和可执行代码都会在进入场景语义之前被拒绝，因此用户只能表达“想要什么”，不能偷渡“后端怎样实现”。",
    input: "原始 request + seed",
    output: "有界的语义意图",
    failure: "请求没有越过信任边界",
    art: '<div class="boundary-card allowed"><span>允许</span><b>can on plate</b></div><div class="boundary-line"></div><div class="boundary-card denied"><span>拒绝</span><b>asset_id / pose</b></div>'
  },
  1: {
    kicker: "STAGE 1 · TYPED SCENE SPEC",
    title: "语义被锁进不可变的 SceneSpec。",
    body: "SceneSpec 使用严格 schema 拒绝未知字段，并检查对象唯一性、支撑关系完整性和空间约束是否矛盾。这个阶段只描述物体与关系，不允许出现路径、资产标识、位置或四元数，所以后端实现不能反向污染用户意图。",
    input: "有界语义意图",
    output: "robotwin.scene_spec.v1",
    failure: "语义本身不完整或互相矛盾",
    art: '<div class="spec-sheet"><span>SceneSpec</span><code>objects: [can_1, plate_1]</code><code>relation: on_top_of</code><code>seed: 42</code><b>extra = forbid</b></div>'
  },
  2: {
    kicker: "STAGE 2 · GROUNDING",
    title: "抽象的“罐子”被绑定到真实资产。",
    body: "grounding 会在资产目录中比较 category、语义名称、别名、颜色、材质、碰撞可用性和尺寸信息。相同的 SceneSpec、资产目录与 seed 必须选出相同模型；被淘汰的候选及其原因也会留下记录。",
    input: "SceneSpec + asset catalog",
    output: "可追溯的资产选择",
    failure: "没有资产满足语义与物理要求",
    art: '<div class="asset-candidates"><div><i></i><span>can / model 0</span><b>0.92</b></div><div class="selected"><i></i><span>can / model 3</span><b>0.97</b></div><div><i></i><span>can / model 8</span><b>reject</b></div></div>'
  },
  3: {
    kicker: "STAGE 3 · SOLVE & PACKAGE",
    title: "受限求解器找到可行姿态，再把结果封成包。",
    body: "求解器按支撑深度放置物体，并在目标局部稳定面或容器内部几何中做有限次数的 rejection backtracking。成功结果随后写入 request、SceneSpec、ResolvedScene、回放入口与 package manifest，每个文件都由 SHA-256 绑定。",
    input: "已 grounding 的对象与关系",
    output: "EnvironmentPackage 引用",
    failure: "有限尝试结束后仍没有可行场景",
    art: '<div class="solver-art"><div class="solver-target"><i></i><b>stable surface</b><span class="solver-object"></span></div><div class="solver-trace"><span>attempt 01 · reject</span><span>attempt 02 · reject</span><span>attempt 03 · pass</span></div></div>'
  },
  4: {
    kicker: "STAGE 4 · ROBOTWIN / SAPIEN REPLAY",
    title: "场景进入仿真器，连续物理证据开始产生。",
    body: "replay 从物理释放开始记录，默认等待 900 个仿真步，并在最终 120 步采样接触。视频保留 119 个连续释放帧和一个最终稳定帧，因此验证看到的是动态过程与终态，而不是一张经过挑选的静态截图。",
    input: "EnvironmentPackage + runtime_config",
    output: "runtime_evidence + replay artifacts",
    failure: "没有形成完整、连续、可绑定的证据",
    art: '<div class="timeline-art"><b>release</b><span></span><i>0</i><i>300</i><i>900</i><strong>120-step contact window</strong></div>'
  },
  5: {
    kicker: "STAGE 5 · VALIDATION GATES",
    title: "最终验证把证据翻译成发布前的结构化结论。",
    body: "validate 会验证包、哈希绑定、运行时证据、接触、碰撞、稳定性、包含、可见性和视频。报告状态仍是 pass、incomplete 或 fail；只有这个 Skill 会进一步计算 publishable，而且任何缺失条件都会产生结构化 blocker。",
    input: "包 + runtime evidence + gate profile",
    output: "validation report + publishable",
    failure: "结果得到解释，但不能进入发布",
    art: '<div class="gate-mini"><span class="pass">hash</span><span class="pass">contact</span><span class="pass">stable</span><span class="pass">visible</span><b>publishable?</b></div>'
  }
};

const skillData = {
  compile: {
    ref: "text2env.compile@1.0.0",
    title: "把语义请求变成不可变的场景包引用。",
    description: "compile 复用项目现有的受限解析、资产 grounding、受限求解、builder 和静态 validator。Harness 只为这组既有行为补上稳定的输入、输出、版本和审计边界。",
    rule: "compile 的 RunState 可以是 <b>succeeded</b>，同时静态验证报告仍是 <b>incomplete</b>。前者表示编译接口正常产出了类型化结果；后者表示真实物理证据还没有产生。",
    inputs: ["request · 原始语义文本", "seed · 0 到 2,147,483,647", "asset_catalog · 内容可验证的 ArtifactRef", "generate_missing_assets · 默认 false"],
    outputs: ["scene_spec", "resolved_scene", "environment_package", "static_validation"],
    attempts: "1"
  },
  replay: {
    ref: "text2env.replay@1.0.0",
    title: "把不可变场景包变成连续物理证据。",
    description: "replay 在 RoboTwin/SAPIEN 中加载已经解析好的场景，不重新理解用户文本，也不重新选择资产。它记录释放、沉降、最终接触、可见性、碰撞、姿态与视频，让后续验证拥有可复核的物理事实。",
    rule: "replay 最多尝试 <b>2</b> 次，但只有 blocker 明确标记 <b>retryable=true</b> 时，Registry 才能在相同 run_id 与 invocation_digest 下开始第二次尝试。MCP 和调用方都不能自行增加重试。",
    inputs: ["environment_package · 已哈希绑定的包引用", "precheck_steps · 默认 0", "settle_steps · 默认 900", "contact_window_steps · 默认 120", "video_frames · 默认 120", "fps · 默认 12"],
    outputs: ["runtime_evidence", "replay_artifacts[]"],
    attempts: "2"
  },
  validate: {
    ref: "text2env.validate@1.0.0",
    title: "把包、证据与资格条件合并成发布判断。",
    description: "validate 检查 EnvironmentPackage、每个引用制品的摘要、运行证据绑定、全部物理门控和已注册 Skill 的资格制品。它沿用现有 pass、incomplete、fail 枚举，不再创造第二套验证状态。",
    rule: "validate 即使产生 <b>validation_status=fail</b>，其 RunState 仍可为 <b>succeeded</b>，因为接口已经正确地产生类型化拒绝结果。此时输出 blockers 解释为什么 <b>publishable=false</b>。",
    inputs: ["environment_package", "runtime_evidence", "gate_profile · 默认 robotwin.scene_validation.v1"],
    outputs: ["validation_report", "validation_status", "publishable", "blockers[]"],
    attempts: "1"
  }
};

const scenarioData = {
  compile: {
    label: "场景 A · 编译刚结束",
    explain: "编译接口已经完整返回，但运行时回放尚未开始，所以系统还没有物理证据。",
    run: ["succeeded", "value-good"],
    validation: ["incomplete", "value-warn"],
    publish: ["false", "value-bad"],
    conclusion: "因此，“编译成功”只能证明场景包被正确生成，不能证明场景已经通过物理验证。"
  },
  "validation-fail": {
    label: "场景 B · 验证正常执行，但检查失败",
    explain: "validate 已经读完包与证据，并正常产生了类型化 fail 报告。某个物理门控失败属于预期业务结论，不属于 Harness 崩溃。",
    run: ["succeeded", "value-good"],
    validation: ["fail", "value-bad"],
    publish: ["false", "value-bad"],
    conclusion: "因此，“validate succeeded”表示验证器完成了工作，不表示被验证对象通过了检查。"
  },
  "qualification-missing": {
    label: "场景 C · 物理通过，但资格证据缺失",
    explain: "本次场景的物理检查全部通过，但注册描述符没有提供通过的确定性测试或回归资格制品。",
    run: ["succeeded", "value-good"],
    validation: ["pass", "value-good"],
    publish: ["false", "value-bad"],
    conclusion: "因此，“validation pass”仍不足以单独获得发布资格，Skill 本身也必须证明实现具备稳定资格。"
  },
  publishable: {
    label: "场景 D · 全部发布条件成立",
    explain: "三个精确版本执行成功，包与证据绑定正确，物理门控通过，Skill 资格制品和来源记录也都完整。",
    run: ["succeeded", "value-good"],
    validation: ["pass", "value-good"],
    publish: ["true", "value-good"],
    conclusion: "因此，本次结果具备发布资格。契约仍然不会执行真正的发布动作，也不会产生 published 状态。"
  }
};

const blockerData = {
  HARN_INPUT_INVALID: {
    stage: "PRECHECK · RUN BLOCKER",
    message: "调用参数没有通过严格 schema 验证。Registry 不会猜测缺失的必填值，也不会忽略未知字段。",
    status: "blocked", retry: "false", digest: "null"
  },
  HARN_VERSION_UNSUPPORTED: {
    stage: "RESOLUTION · RUN BLOCKER",
    message: "请求的精确版本不存在，或者相同的不可变 Skill 身份曾被不同描述符或实现摘要重新注册。Registry 禁止 latest 与静默回退。",
    status: "blocked", retry: "false", digest: "null"
  },
  HARN_DEPENDENCY_UNAVAILABLE: {
    stage: "PRECHECK · RUN BLOCKER",
    message: "调用所需依赖的名称、版本或 SHA-256 无法解析。依赖身份不完整时，Registry 不会创建 Invocation。",
    status: "blocked", retry: "false", digest: "null"
  },
  T2E_REQUEST_REJECTED: {
    stage: "COMPILE · RUN BLOCKER",
    message: "请求越过了受限 prompt 或 SceneSpec 边界，例如携带路径、后端字段、坐标或不受支持的关系。",
    status: "blocked", retry: "false", digest: "已计算"
  },
  T2E_SOLVER_EXHAUSTED: {
    stage: "COMPILE · RUN BLOCKER",
    message: "受限求解器已经用完有限采样与回退预算，但没有得到满足稳定面、包含和空间约束的 resolved scene。",
    status: "blocked", retry: "false", digest: "已计算"
  },
  T2E_REPLAY_FAILED: {
    stage: "REPLAY · RUN BLOCKER",
    message: "RoboTwin/SAPIEN 回放没有生成完整证据。这个 blocker 默认允许 Registry 在同一调用身份下执行最多一次额外尝试。",
    status: "blocked", retry: "true", digest: "保持不变"
  },
  T2E_VALIDATION_FAILED: {
    stage: "VALIDATE · OUTPUT BLOCKER",
    message: "一个或多个必需门控失败。validate 正常返回类型化 fail 报告，blocker 位于 validate 输出中，而 RunState 可以保持 succeeded。",
    status: "succeeded", retry: "false", digest: "已计算"
  }
};

const ledgerPages = ["one", "two", "three"];
const ledgerSummaries = {
  one: "先建立基础认识：Asset Ledger 是每个资产的权威档案。",
  two: "再划清边界：Ledger 管资产事实，Harness 管一次 Skill 调用的执行事实。",
  three: "最后形成开发约束：固定 catalog 快照，并把 ledger 到 catalog 的投影来源一起绑定。"
};

let currentLedgerPage = 0;

function showLedgerPage(index) {
  currentLedgerPage = Math.max(0, Math.min(index, ledgerPages.length - 1));
  const page = ledgerPages[currentLedgerPage];
  document.querySelectorAll(".ledger-page-tab").forEach((tab) => {
    const active = tab.dataset.ledgerPage === page;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", active ? "true" : "false");
  });
  document.querySelectorAll(".ledger-page").forEach((panel) => {
    const active = panel.dataset.ledgerPanel === page;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
  document.getElementById("ledgerPageCount").textContent = `${String(currentLedgerPage + 1).padStart(2, "0")} / 03`;
  document.getElementById("ledgerPageSummary").textContent = ledgerSummaries[page];
  document.getElementById("ledgerPrev").disabled = currentLedgerPage === 0;
  document.getElementById("ledgerNext").disabled = currentLedgerPage === ledgerPages.length - 1;
}

document.querySelectorAll(".ledger-page-tab").forEach((tab) => {
  tab.addEventListener("click", () => showLedgerPage(ledgerPages.indexOf(tab.dataset.ledgerPage)));
});

document.getElementById("ledgerPrev").addEventListener("click", () => showLedgerPage(currentLedgerPage - 1));
document.getElementById("ledgerNext").addEventListener("click", () => showLedgerPage(currentLedgerPage + 1));

const stageTabs = document.querySelectorAll(".stage-tab");
stageTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    const data = stageData[tab.dataset.stage];
    stageTabs.forEach((item) => {
      item.classList.toggle("active", item === tab);
      item.setAttribute("aria-selected", item === tab ? "true" : "false");
    });
    document.getElementById("stageKicker").textContent = data.kicker;
    document.getElementById("stageIndex").textContent = String(tab.dataset.stage).padStart(2, "0");
    document.getElementById("stageTitle").textContent = data.title;
    document.getElementById("stageBody").textContent = data.body;
    document.getElementById("stageInput").textContent = data.input;
    document.getElementById("stageOutput").textContent = data.output;
    document.getElementById("stageFailure").textContent = data.failure;
    document.getElementById("stageArt").innerHTML = data.art;
  });
});

document.querySelectorAll(".skill-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    const data = skillData[tab.dataset.skill];
    document.querySelectorAll(".skill-tab").forEach((item) => item.classList.toggle("active", item === tab));
    document.getElementById("skillRef").textContent = data.ref;
    document.getElementById("skillTitle").textContent = data.title;
    document.getElementById("skillDescription").textContent = data.description;
    document.querySelector("#skillRule p").innerHTML = data.rule;
    document.getElementById("skillInputs").innerHTML = data.inputs.map((item) => `<li>${item}</li>`).join("");
    document.getElementById("skillOutputs").innerHTML = data.outputs.map((item) => `<li>${item}</li>`).join("");
    document.getElementById("skillAttempts").textContent = data.attempts;
  });
});

document.querySelectorAll(".truth-option").forEach((option) => {
  option.addEventListener("click", () => {
    const data = scenarioData[option.dataset.scenario];
    document.querySelectorAll(".truth-option").forEach((item) => item.classList.toggle("active", item === option));
    document.getElementById("scenarioLabel").textContent = data.label;
    document.getElementById("scenarioExplain").textContent = data.explain;
    setMetric("runValue", data.run);
    setMetric("validationValue", data.validation);
    setMetric("publishValue", data.publish);
    document.getElementById("scenarioConclusion").textContent = data.conclusion;
  });
});

function setMetric(id, value) {
  const element = document.getElementById(id);
  element.textContent = value[0];
  element.className = value[1];
}

document.querySelectorAll(".gate").forEach((gate) => {
  gate.addEventListener("click", () => {
    gate.classList.toggle("active");
    gate.setAttribute("aria-pressed", gate.classList.contains("active") ? "true" : "false");
    gate.querySelector(":scope > b").textContent = gate.classList.contains("active") ? "PASS" : "BLOCK";
    updatePublishMeter();
  });
});

function updatePublishMeter() {
  const gates = [...document.querySelectorAll(".gate")];
  const passed = gates.filter((gate) => gate.classList.contains("active")).length;
  const meter = document.querySelector(".publish-meter");
  document.getElementById("gateCount").textContent = `${passed} / ${gates.length}`;
  const isPublishable = passed === gates.length;
  meter.classList.toggle("failed", !isPublishable);
  document.getElementById("publishableValue").textContent = `publishable = ${isPublishable}`;
  document.getElementById("publishableReason").textContent = isPublishable
    ? "六项发布前置条件全部成立，因此本次结果具备发布资格。"
    : `仍有 ${gates.length - passed} 项前置条件不成立。validate 必须返回 publishable=false，并至少给出一个结构化 blocker。`;
}

document.querySelectorAll(".blocker-code").forEach((button) => {
  button.addEventListener("click", () => {
    const data = blockerData[button.dataset.code];
    document.querySelectorAll(".blocker-code").forEach((item) => item.classList.toggle("active", item === button));
    document.getElementById("blockerStage").textContent = data.stage;
    document.getElementById("blockerCode").textContent = button.dataset.code;
    document.getElementById("blockerMessage").textContent = data.message;
    document.getElementById("blockerStatus").textContent = data.status;
    document.getElementById("blockerRetry").textContent = data.retry;
    document.getElementById("blockerDigest").textContent = data.digest;
  });
});

const hashState = {
  runId: false,
  uri: false,
  seed: false,
  space: false,
  dependency: false
};

let baselineDigest = "";

document.querySelectorAll("[data-hash-change]").forEach((button) => {
  button.addEventListener("click", () => {
    const key = button.dataset.hashChange;
    hashState[key] = !hashState[key];
    button.classList.toggle("active", hashState[key]);
    renderDigest();
  });
});

function invocationPayload() {
  const request = `Place a can on top of a plate.${hashState.space ? " " : ""}`;
  return {
    skill_id: "text2env.compile",
    skill_version: "1.0.0",
    effective_parameters: {
      request,
      seed: hashState.seed ? 43 : 42,
      asset_catalog: {
        media_type: "application/json",
        schema_version: "robotwin.asset_catalog.v1",
        sha256: hashState.dependency ? "47c0bb75..." : "8ba15e84..."
      },
      config: {
        generate_missing_assets: false
      }
    },
    dependencies: [
      {
        name: "robotwin_asset_catalog",
        version: "2026-07-19",
        sha256: hashState.dependency ? "47c0bb75..." : "8ba15e84..."
      }
    ],
    max_attempts: 1
  };
}

async function sha256(value) {
  if (window.crypto && window.crypto.subtle) {
    const encoded = new TextEncoder().encode(value);
    const hash = await window.crypto.subtle.digest("SHA-256", encoded);
    return [...new Uint8Array(hash)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  }
  let first = 2166136261;
  let second = 2246822519;
  for (let index = 0; index < value.length; index += 1) {
    first = Math.imul(first ^ value.charCodeAt(index), 16777619);
    second = Math.imul(second ^ value.charCodeAt(index), 3266489917);
  }
  const part = `${(first >>> 0).toString(16).padStart(8, "0")}${(second >>> 0).toString(16).padStart(8, "0")}`;
  return part.repeat(4);
}

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === "object") {
    return Object.keys(value)
      .sort()
      .reduce((result, key) => {
        result[key] = canonicalize(value[key]);
        return result;
      }, {});
  }
  return value;
}

async function renderDigest() {
  const payload = canonicalize(invocationPayload());
  const canonical = JSON.stringify(payload);
  const digest = await sha256(canonical);
  if (!baselineDigest) baselineDigest = digest;

  document.getElementById("digestPayload").textContent = JSON.stringify(payload, null, 2);
  document.getElementById("digestValue").textContent = digest;

  const identityChanged = hashState.seed || hashState.space || hashState.dependency;
  const locationOnly = (hashState.runId || hashState.uri) && !identityChanged;
  const status = document.getElementById("digestStatus");
  const reason = document.getElementById("digestReason");

  if (identityChanged) {
    status.textContent = "调用身份已改变";
    reason.textContent = "seed、请求原文或依赖摘要进入规范载荷，因此任何一项变化都会产生新的 invocation_digest。";
  } else if (locationOnly) {
    status.textContent = "调用身份保持不变";
    reason.textContent = "run_id 只用于审计，URI 只用于定位；制品内容身份未变，所以 invocation_digest 保持不变。";
  } else {
    status.textContent = "基准调用身份";
    reason.textContent = "run_id、时间戳、事件、输出目录和 URI 不进入 invocation_digest。";
  }

  document.getElementById("digestValue").style.color = digest === baselineDigest ? "var(--acid)" : "var(--orange-soft)";
}

renderDigest();

const navToggle = document.getElementById("navToggle");
const siteNav = document.getElementById("siteNav");
navToggle.addEventListener("click", () => {
  const open = navToggle.getAttribute("aria-expanded") === "true";
  navToggle.setAttribute("aria-expanded", open ? "false" : "true");
  siteNav.classList.toggle("open", !open);
});

siteNav.querySelectorAll("a").forEach((link) => {
  link.addEventListener("click", () => {
    siteNav.classList.remove("open");
    navToggle.setAttribute("aria-expanded", "false");
  });
});

window.addEventListener("load", () => {
  if (!window.location.hash) return;
  const target = document.querySelector(window.location.hash);
  if (!target) return;
  const root = document.documentElement;
  const previousBehavior = root.style.scrollBehavior;
  root.style.scrollBehavior = "auto";
  requestAnimationFrame(() => {
    target.scrollIntoView({ block: "start" });
    root.style.scrollBehavior = previousBehavior;
  });
});

const progress = document.getElementById("readingProgress");
window.addEventListener("scroll", () => {
  const maximum = document.documentElement.scrollHeight - window.innerHeight;
  const percent = maximum > 0 ? (window.scrollY / maximum) * 100 : 0;
  progress.style.width = `${percent}%`;
}, { passive: true });

const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (entry.isIntersecting) {
      entry.target.classList.add("visible");
      revealObserver.unobserve(entry.target);
    }
  });
}, { threshold: 0.08, rootMargin: "0px 0px -30px" });

document.querySelectorAll(".reveal").forEach((element) => revealObserver.observe(element));
