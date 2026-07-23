import { api } from "./api.js";
import { el, showToast } from "./dom.js";
import { state } from "./store.js";

export function populateFoodSelect(preferredKey = null) {
  const select = el("foodSelect");
  const desiredValue = preferredKey || localStorage.getItem("elfieLab.foodKey") || select.value;
  select.replaceChildren();
  state.foods.forEach((food) => {
    const option = document.createElement("option");
    option.value = food.key;
    option.disabled = food.key !== "mock" && !food.ready_for_attempt;
    const statusMark = !food.ready_for_attempt
      ? " · 未就绪"
      : !food.primary_ready && food.fallback_ready
        ? " · 可降级"
        : "";
    option.textContent = `${food.display_name}${statusMark}`;
    select.append(option);
  });
  const desiredFood = state.foods.find(
    (food) => food.key === desiredValue && food.ready_for_attempt,
  );
  const fallbackFood = state.foods.find((food) => food.ready_for_attempt);
  select.value = (desiredFood || fallbackFood)?.key || "";
  localStorage.setItem("elfieLab.foodKey", select.value);
  renderFoodSetupList();
}

export function updateModelHint() {
  const hint = el("modelHint");
  hint.classList.remove("is-ready", "is-error");
  const selectedKey = el("foodSelect").value;
  const food = state.foods.find((item) => item.key === selectedKey);
  if (!food) {
    hint.textContent = "没有已就绪的粮食";
    hint.classList.add("is-error");
    return;
  }
  localStorage.setItem("elfieLab.foodKey", selectedKey);
  if (food.key === "mock") {
    hint.textContent = "elfie-mock · 不调用外部服务";
    return;
  }
  const readiness = !food.ready_for_attempt
    ? food.unavailable_reason
    : food.primary_ready
      ? "主模型已就绪"
      : food.fallback_ready
        ? "主模型未就绪，将尝试降级模型"
        : "没有可用模型";
  hint.textContent = `${food.model} · ${food.description} · ${readiness}`;
  hint.classList.add(food.ready_for_attempt ? "is-ready" : "is-error");
}

function renderFoodSetupList() {
  const container = el("foodSetupList");
  const commandFoods = new Map();
  const configureCommand = state.configurationCommand;
  state.foods.forEach((food) => {
    (food.setup_commands || []).forEach((command) => {
      if (!commandFoods.has(command)) commandFoods.set(command, []);
      commandFoods.get(command).push(food.display_name);
    });
  });
  container.replaceChildren();
  if (commandFoods.size && configureCommand) {
    appendSetupCommand(container, "完整 Runtime Lab：", configureCommand);
  }
  commandFoods.forEach((names, command) => {
    if (command !== configureCommand) {
      appendSetupCommand(container, `${[...new Set(names)].join("、")}：`, command);
    }
  });
  container.hidden = commandFoods.size === 0;
}

function appendSetupCommand(container, labelText, command) {
  const row = document.createElement("div");
  const label = document.createElement("span");
  label.textContent = labelText;
  const code = document.createElement("code");
  code.textContent = command;
  row.append(label, code);
  container.append(row);
}

export async function refreshFoods(preferredKey = null) {
  try {
    const data = await api("/api/runtime/foods");
    state.foods = data.items || [];
    state.configurationCommand = data.configuration_command || "";
    populateFoodSelect(preferredKey);
    updateModelHint();
    return true;
  } catch (error) {
    showToast(error.message, true);
    return false;
  }
}
