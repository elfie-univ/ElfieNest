(function () {
  function escapeClassPart(value, fallback) {
    return String(value || fallback).replace(/[^a-z0-9_-]/gi, "");
  }

  function avatarClassName(elfie, extraClass) {
    return [
      "elfie-avatar3d",
      `anatomy-${escapeClassPart(elfie?.anatomy, "biped")}`,
      `height-${escapeClassPart(elfie?.height, "standard")}`,
      `build-${escapeClassPart(elfie?.build, "standard")}`,
      extraClass || "",
    ].filter(Boolean).join(" ");
  }

  function avatarPartsMarkup() {
    return `
      <span class="avatar-ears"></span>
      <span class="avatar-head"></span>
      <span class="avatar-body"></span>
      <span class="avatar-legs"></span>
      <span class="avatar-shadow"></span>
    `;
  }

  function avatarMarkup(elfie, extraClass) {
    return `
      <div class="${avatarClassName(elfie, extraClass)}" aria-hidden="true">
        ${avatarPartsMarkup()}
      </div>
    `;
  }

  function setRotation(node, degrees) {
    node.style.setProperty("--avatar-rotate-y", `${degrees}deg`);
  }

  function bindRotation(node, initialRotation = -12) {
    let rotation = initialRotation;
    let startX = 0;
    let startRotation = rotation;
    let dragging = false;
    setRotation(node, rotation);

    node.addEventListener("pointerdown", (event) => {
      dragging = true;
      startX = event.clientX;
      startRotation = rotation;
      node.classList.add("dragging");
      node.setPointerCapture(event.pointerId);
    });
    node.addEventListener("pointermove", (event) => {
      if (!dragging) return;
      rotation = Math.max(-70, Math.min(70, startRotation + (event.clientX - startX) * 0.55));
      setRotation(node, rotation);
    });
    ["pointerup", "pointercancel"].forEach((type) => {
      node.addEventListener(type, () => {
        dragging = false;
        node.classList.remove("dragging");
      });
    });

    return {
      reset(nextRotation = initialRotation) {
        rotation = nextRotation;
        setRotation(node, rotation);
      },
    };
  }

  window.ElfieAvatar3D = {
    bindRotation,
    className: avatarClassName,
    markup: avatarMarkup,
    partsMarkup: avatarPartsMarkup,
  };
})();
