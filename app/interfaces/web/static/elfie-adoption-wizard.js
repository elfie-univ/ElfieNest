(function () {
  const consoleApi = window.ElfieNestConsole;
  const avatar = window.ElfieAvatar3D;
  const options = window.ElfieAdoptionOptions;
  const form = document.querySelector("#adoption-form");
  if (!consoleApi || !avatar || !options || !form) return;

  const state = {
    step: 0,
    species: "fox",
    height: "standard",
    build: "standard",
    personality: "活泼好动",
    name: "",
  };

  const steps = ["选择动物物种", "调整高矮胖瘦", "给精灵起名字", "选择性格", "预览 3D 形象", "确认配置"];
  const lastStep = steps.length - 1;
  const byId = (id) => document.getElementById(id);
  const panels = Array.from(document.querySelectorAll("[data-adoption-panel]"));
  const nameInput = byId("adopt-name");
  const nextButton = byId("adoption-next-button");
  const prevButton = byId("adoption-prev-button");
  const submitButton = byId("adoption-submit-button");
  const message = byId("adoption-message");
  const stepCount = byId("adoption-step-count");
  const stepTitle = byId("adoption-step-title");
  const stepMeter = byId("adoption-step-meter");
  const footerStep = byId("adoption-footer-step");
  const previewAvatar = byId("adoption-preview-avatar");
  const previewRotation = previewAvatar ? avatar.bindRotation(previewAvatar, -12) : null;

  function escapeHtml(value) {
    return consoleApi.escapeHtml(value);
  }

  function setMessage(text, kind = "info") {
    if (!message) return;
    message.textContent = text;
    message.style.color = kind === "error" ? "var(--status-error)" : kind === "success" ? "var(--status-success)" : "var(--text-secondary)";
  }

  function optionButton(group, option, selected) {
    return `
      <button class="choice-card ${selected ? "active" : ""}" type="button" data-choice-group="${group}" data-choice-value="${escapeHtml(option.value)}">
        <strong>${escapeHtml(option.label)}</strong>
        <span>${escapeHtml(option.detail)}</span>
      </button>
    `;
  }

  function speciesButton(value) {
    const option = options.speciesOption(value);
    return `
      <button class="choice-card species-choice ${state.species === value ? "active" : ""}" type="button" data-choice-group="species" data-choice-value="${escapeHtml(value)}">
        <span class="choice-avatar">
          ${avatar.markup({ species: value, height: "standard", build: "standard" })}
        </span>
        <strong>${escapeHtml(option.label)}</strong>
        <span>${escapeHtml(option.detail)}</span>
      </button>
    `;
  }

  function personalityOptions() {
    const info = consoleApi.getAdoptionInfo() || {};
    const styles = Array.isArray(info.personality_styles) && info.personality_styles.length
      ? info.personality_styles
      : ["活泼好动", "安静温顺", "好奇探索", "胆小害羞", "傲娇独立", "完全随机"];
    if (!styles.includes(state.personality)) {
      state.personality = styles[0] || "活泼好动";
    }
    return styles.map((style) => optionButton("personality", {
      value: style,
      label: style,
      detail: options.personalityDetail(style),
    }, state.personality === style)).join("");
  }

  function selectedElfie() {
    return {
      species: state.species,
      height: state.height,
      build: state.build,
    };
  }

  function selectedName() {
    const typed = (nameInput?.value || "").trim();
    return typed || state.name || `新精灵${consoleApi.getElfieCount() + 1}`;
  }

  function renderChoices() {
    const info = consoleApi.getAdoptionInfo() || {};
    const species = Array.isArray(info.species_ids) && info.species_ids.length
      ? info.species_ids
      : ["dog", "fox"];
    if (!species.includes(state.species)) {
      state.species = species[0] || "fox";
    }
    const anatomyNode = byId("adoption-anatomy-options");
    if (anatomyNode) anatomyNode.innerHTML = species.map(speciesButton).join("");

    const heightNode = byId("adoption-height-options");
    if (heightNode) {
      heightNode.innerHTML = options.heightOptions.map((option) => optionButton("height", option, state.height === option.value)).join("");
    }

    const buildNode = byId("adoption-build-options");
    if (buildNode) {
      buildNode.innerHTML = options.buildOptions.map((option) => optionButton("build", option, state.build === option.value)).join("");
    }

    const personalityNode = byId("adoption-personality-options");
    if (personalityNode) personalityNode.innerHTML = personalityOptions();
  }

  function reviewRows(compact = false) {
    const species = consoleApi.labelForSpecies(state.species);
    const appearance = consoleApi.labelForAppearance(state.height, state.build);
    const rows = [
      ["名字", selectedName()],
      ["物种", species],
      ["体态", appearance],
      ["性格", state.personality],
      ["配置状态", compact ? "确认后锁定" : "领养后不可修改"],
    ];
    return rows.map(([label, value]) => `
      <div>
        <dt>${escapeHtml(label)}</dt>
        <dd>${escapeHtml(value)}</dd>
      </div>
    `).join("");
  }

  function renderPreview() {
    if (previewAvatar) {
      previewAvatar.className = avatar.className(selectedElfie(), "avatar-preview avatar-model");
      previewAvatar.innerHTML = avatar.partsMarkup();
    }
    const previewFacts = byId("adoption-preview-facts");
    if (previewFacts) previewFacts.innerHTML = reviewRows(true);
    const reviewList = byId("adoption-review-list");
    if (reviewList) reviewList.innerHTML = reviewRows(false);
  }

  function renderProgress() {
    const humanStep = state.step + 1;
    const title = steps[state.step] || "";
    if (stepCount) stepCount.textContent = `第 ${humanStep} 步 / 共 ${steps.length} 步`;
    if (stepTitle) stepTitle.textContent = title;
    if (stepMeter) {
      stepMeter.max = String(steps.length);
      stepMeter.value = humanStep;
      stepMeter.textContent = `${humanStep}/${steps.length}`;
    }
    if (footerStep) footerStep.textContent = `第 ${humanStep} / ${steps.length} 步 · ${title}`;
  }

  function resetPanelScroll() {
    form.scrollTop = 0;
    requestAnimationFrame(() => {
      form.scrollTop = 0;
    });
  }

  function setStep(nextStep) {
    state.step = Math.max(0, Math.min(lastStep, nextStep));
    form.dataset.step = String(state.step);
    panels.forEach((panel) => {
      panel.classList.toggle("active", Number(panel.dataset.adoptionPanel || 0) === state.step);
    });
    if (prevButton) prevButton.disabled = state.step === 0;
    if (nextButton) nextButton.hidden = state.step === lastStep;
    if (submitButton) submitButton.hidden = state.step !== lastStep;
    renderProgress();
    setMessage("");
    renderPreview();
    resetPanelScroll();
  }

  function resetWizard() {
    state.step = 0;
    state.species = "fox";
    state.height = "standard";
    state.build = "standard";
    state.personality = "活泼好动";
    state.name = "";
    previewRotation?.reset(-12);
    if (nameInput) nameInput.value = "";
    renderChoices();
    setStep(0);
  }

  async function submitAdoption() {
    state.name = selectedName();
    setMessage("正在领养...");
    if (submitButton) submitButton.disabled = true;
    try {
      await consoleApi.fetchJson("/api/user/adopt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: state.name,
          species_id: state.species,
          personality_style: state.personality,
          height: state.height,
          build: state.build,
        }),
      });
      setMessage("领养成功", "success");
      await consoleApi.loadElves();
      await consoleApi.loadAdoptionInfo();
      consoleApi.addSystemNotice(`已领养 ${state.name}。`);
      setTimeout(() => {
        consoleApi.closeDrawers();
        resetWizard();
      }, 900);
    } catch (error) {
      setMessage(error.message || "领养失败", "error");
    } finally {
      if (submitButton) submitButton.disabled = false;
    }
  }

  form.addEventListener("click", (event) => {
    const choice = event.target.closest("[data-choice-group]");
    if (choice) {
      const group = choice.dataset.choiceGroup;
      const value = choice.dataset.choiceValue;
      if (group && value && group in state) {
        state[group] = value;
        renderChoices();
        renderPreview();
      }
      return;
    }

  });

  nextButton?.addEventListener("click", () => setStep(state.step + 1));
  prevButton?.addEventListener("click", () => setStep(state.step - 1));
  nameInput?.addEventListener("input", () => {
    state.name = selectedName();
    renderPreview();
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.step !== lastStep) {
      setStep(state.step + 1);
      return;
    }
    await submitAdoption();
  });

  window.addEventListener("elfienest:adoption-info", () => {
    renderChoices();
    renderPreview();
  });

  resetWizard();
})();
