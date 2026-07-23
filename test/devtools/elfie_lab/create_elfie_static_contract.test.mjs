import assert from "node:assert/strict";
import test from "node:test";

const nodes = new Map();

function fakeNode(value = "") {
  return {
    value,
    hidden: false,
    textContent: "",
    children: [],
    className: "",
    style: {},
    classList: { toggle() {} },
    addEventListener() {},
    append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.children = children; },
    setAttribute() {},
    focus() {},
    querySelector() {
      if (!this.submitButton) this.submitButton = fakeNode();
      return this.submitButton;
    },
    reset() { this.wasReset = true; },
  };
}

globalThis.document = {
  createElement: () => fakeNode(),
  getElementById(id) {
    if (!nodes.has(id)) nodes.set(id, fakeNode());
    return nodes.get(id);
  },
};
globalThis.requestAnimationFrame = (callback) => callback();

const createModule = await import(
  "../../../devtools/elfie_lab/static/create-elfie.js"
);

test("buildCreateElfiePayload reads the required natural-language profile", () => {
  document.getElementById("createName").value = "绒绒";
  document.getElementById("createSpecies").value = "fox";
  document.getElementById("createAgeYears").value = "2.5";
  document.getElementById("createDescription").value = "陪伴我测试日常交互";
  document.getElementById("createAppearanceDescription").value = "白色耳尖";
  document.getElementById("createPersonalityDescription").value = "温柔安静";

  const payload = createModule.buildCreateElfiePayload();

  assert.deepEqual(payload, {
    name: "绒绒",
    species_id: "fox",
    age_years: 2.5,
    description: "陪伴我测试日常交互",
    appearance_description: "白色耳尖",
    personality_description: "温柔安静",
  });
});

test("openCreate clears data from the previous adoption", () => {
  const form = document.getElementById("createForm");
  form.wasReset = false;

  createModule.openCreate();

  assert.equal(form.wasReset, true);
  assert.equal(document.getElementById("createModal").hidden, false);
});

test("buildCreateElfiePayload rejects an invalid age", () => {
  document.getElementById("createAgeYears").value = "0";

  assert.throws(
    () => createModule.buildCreateElfiePayload(),
    /年龄必须大于 0/,
  );
});

test("createElfie ignores a repeated submit while creation is in flight", async () => {
  document.getElementById("createName").value = "绒绒";
  document.getElementById("createSpecies").value = "fox";
  document.getElementById("createAgeYears").value = "2.5";
  document.getElementById("createDescription").value = "陪伴我测试日常交互";
  document.getElementById("createAppearanceDescription").value = "白色耳尖";
  document.getElementById("createPersonalityDescription").value = "温柔安静";

  let postCount = 0;
  globalThis.fetch = async (path, options = {}) => {
    if (options.method === "POST") postCount += 1;
    return {
      ok: true,
      async json() {
        return path === "/api/elfies"
          ? (options.method === "POST" ? { elfie_id: "elfie_test" } : { items: [] })
          : {};
      },
    };
  };
  createModule.configureCreateElfie(async () => {});
  const event = { preventDefault() {} };

  await Promise.all([
    createModule.createElfie(event),
    createModule.createElfie(event),
  ]);

  assert.equal(postCount, 1);
  assert.equal(document.getElementById("createForm").submitButton.disabled, false);
});
