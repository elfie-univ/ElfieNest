import DefaultTheme from "vitepress/theme";
import { nextTick } from "vue";
import "./custom.css";

let cleanupStoryExperience: (() => void) | undefined;
let cleanupHomeExperience: (() => void) | undefined;
let homeExperiencePath: string | undefined;

function setupHomeExperience() {
  const home = document.querySelector<HTMLElement>(".VPHome");
  if (!home || !document.body) {
    cleanupHomeExperience?.();
    cleanupHomeExperience = undefined;
    return;
  }

  if (
    homeExperiencePath === window.location.pathname &&
    home.classList.contains("home-scroll") &&
    document.body.classList.contains("home-mode")
  ) {
    return;
  }

  cleanupHomeExperience?.();
  cleanupHomeExperience = undefined;

  const hero = home?.querySelector<HTMLElement>(".VPHero");
  const features = home?.querySelector<HTMLElement>(".VPHomeFeatures");
  const download = home?.querySelector<HTMLElement>(".home-download");
  const contribute = home?.querySelector<HTMLElement>(".home-contribute");

  if (!hero || !features || !download || !contribute) {
    window.setTimeout(setupHomeExperience, 80);
    return;
  }

  const heroPage = document.createElement("section");
  heroPage.className = "home-scroll__page home-scroll__page--hero";
  heroPage.id = "home";
  heroPage.setAttribute("aria-label", "Home");
  home.insertBefore(heroPage, hero);
  heroPage.append(hero, features);

  download.classList.add("home-scroll__page", "home-scroll__page--download");
  download.id = "download";
  contribute.classList.add("home-scroll__page", "home-scroll__page--community");
  contribute.id = "community";

  const pages = [heroPage, download, contribute];
  let activeIndex = 0;
  let wheelLocked = false;
  let wheelUnlockTimer: number | undefined;
  home.classList.add("home-scroll");
  home.dataset.homeScroll = "";

  const timeline = document.createElement("nav");
  timeline.className = "home-timeline";
  timeline.setAttribute("aria-label", "Homepage sections");
  const dots = pages.map((page, index) => {
    const dot = document.createElement("a");
    dot.className = "home-timeline__dot";
    dot.href = `#${page.id}`;
    dot.setAttribute("aria-label", `Go to section ${index + 1}`);
    dot.dataset.homeIndex = String(index);
    timeline.append(dot);
    return dot;
  });
  document.body.append(timeline);
  document.body.classList.add("home-mode");
  homeExperiencePath = window.location.pathname;

  const updateLanguageLinks = (index: number) => {
    const section = pages[index]?.id ?? "home";
    document.querySelectorAll<HTMLAnchorElement>(".VPNavBarTranslations a[href]").forEach((link) => {
      const target = new URL(link.href, window.location.origin);
      target.hash = section === "home" ? "" : section;
      link.href = `${target.pathname}${target.search}${target.hash}`;
    });
  };

  const setActive = (index: number) => {
    activeIndex = Math.max(0, Math.min(pages.length - 1, index));
    dots.forEach((dot, dotIndex) => {
      dot.classList.toggle("is-active", dotIndex === activeIndex);
    });
    updateLanguageLinks(activeIndex);
  };
  setActive(0);

  const pageTop = (page: HTMLElement) => {
    const homeRect = home.getBoundingClientRect();
    const pageRect = page.getBoundingClientRect();
    return pageRect.top - homeRect.top + home.scrollTop;
  };

  const goToPage = (index: number) => {
    const targetIndex = Math.max(0, Math.min(pages.length - 1, index));
    if (targetIndex === activeIndex || wheelLocked) return;

    wheelLocked = true;
    setActive(targetIndex);
    window.history.replaceState(null, "", `#${pages[targetIndex].id}`);
    home.scrollTo({ top: pageTop(pages[targetIndex]), behavior: "smooth" });

    if (wheelUnlockTimer !== undefined) window.clearTimeout(wheelUnlockTimer);
    wheelUnlockTimer = window.setTimeout(() => {
      wheelLocked = false;
      wheelUnlockTimer = undefined;
    }, 850);
  };

  const onWheel = (event: WheelEvent) => {
    const direction = Math.sign(event.deltaY);
    if (!direction) return;
    const targetIndex = activeIndex + direction;
    if (targetIndex < 0 || targetIndex >= pages.length) return;
    event.preventDefault();
    goToPage(targetIndex);
  };

  const onDotClick = (event: MouseEvent) => {
    event.preventDefault();
    const dot = event.currentTarget as HTMLAnchorElement;
    goToPage(Number(dot.dataset.homeIndex ?? 0));
  };
  dots.forEach((dot) => dot.addEventListener("click", onDotClick));
  window.addEventListener("wheel", onWheel, { passive: false });

  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];
      if (visible) setActive(pages.indexOf(visible.target as HTMLElement));
    },
    { root: home, threshold: [0.35, 0.55, 0.75] }
  );
  pages.forEach((page) => observer.observe(page));

  const hashIndex = pages.findIndex((page) => page.id === window.location.hash.slice(1));
  if (hashIndex >= 0) {
    setActive(hashIndex);
    window.requestAnimationFrame(() => {
      home.scrollTo({ top: pageTop(pages[hashIndex]), behavior: "auto" });
    });
  }

  const select = download.querySelector<HTMLSelectElement>("[data-home-platform-select]");
  const platformIcon = download.querySelector<HTMLElement>("[data-home-platform-icon]");
  const platformName = download.querySelector<HTMLElement>("[data-home-platform-name]");
  const platformHint = `${navigator.platform} ${navigator.userAgent}`.toLowerCase();
  if (select) {
    if (platformHint.includes("win")) select.value = "windows";
    else if (platformHint.includes("linux")) select.value = "linux";
    else if (platformHint.includes("mac")) select.value = "macos-arm";

    const updatePlatform = () => {
      const option = select.selectedOptions[0];
      if (!option) return;
      if (platformIcon) platformIcon.textContent = option.dataset.icon ?? "";
      if (platformName) platformName.textContent = option.dataset.label ?? option.textContent?.trim() ?? "";
    };
    select.addEventListener("change", updatePlatform);
    updatePlatform();

    cleanupHomeExperience = () => {
      observer.disconnect();
      dots.forEach((dot) => dot.removeEventListener("click", onDotClick));
      window.removeEventListener("wheel", onWheel);
      if (wheelUnlockTimer !== undefined) window.clearTimeout(wheelUnlockTimer);
      wheelUnlockTimer = undefined;
      wheelLocked = false;
      select.removeEventListener("change", updatePlatform);
      timeline.remove();
      home.insertBefore(hero, heroPage);
      home.insertBefore(features, heroPage);
      heroPage.remove();
      download.classList.remove("home-scroll__page", "home-scroll__page--download");
      contribute.classList.remove("home-scroll__page", "home-scroll__page--community");
      home.classList.remove("home-scroll");
      delete home.dataset.homeScroll;
      document.body.classList.remove("home-mode");
      homeExperiencePath = undefined;
    };
  } else {
    cleanupHomeExperience = () => {
      observer.disconnect();
      dots.forEach((dot) => dot.removeEventListener("click", onDotClick));
      window.removeEventListener("wheel", onWheel);
      if (wheelUnlockTimer !== undefined) window.clearTimeout(wheelUnlockTimer);
      wheelUnlockTimer = undefined;
      wheelLocked = false;
      timeline.remove();
      home.insertBefore(hero, heroPage);
      home.insertBefore(features, heroPage);
      heroPage.remove();
      download.classList.remove("home-scroll__page", "home-scroll__page--download");
      contribute.classList.remove("home-scroll__page", "home-scroll__page--community");
      home.classList.remove("home-scroll");
      delete home.dataset.homeScroll;
      document.body.classList.remove("home-mode");
      homeExperiencePath = undefined;
    };
  }
}

function setupStoryExperience() {
  cleanupStoryExperience?.();
  cleanupStoryExperience = undefined;

  const root = document.querySelector<HTMLElement>("[data-story-scroll]");
  const chapters = [...document.querySelectorAll<HTMLElement>("[data-story-chapter]")];
  const dots = [...document.querySelectorAll<HTMLAnchorElement>(".story-timeline__dot")];

  if (!root || chapters.length === 0 || dots.length === 0 || !document.body) {
    if (!document.body || !root) window.setTimeout(setupStoryExperience, 80);
    return;
  }

  document.body.classList.add("story-mode");
  window.scrollTo(0, 0);

  const initialHash = window.location.hash.slice(1);
  let activeIndex = Math.max(0, chapters.findIndex((chapter) => chapter.id === initialHash));
  if (activeIndex < 0) activeIndex = 0;
  let locked = false;
  let touchStartY = 0;
  let autoplayTimer: number | undefined;
  let headingFitFrame: number | undefined;
  const autoplayDelay = 8_000;
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const onReducedMotionChange = () => {
    if (prefersReducedMotion.matches) clearAutoplay();
    else scheduleAutoplay();
  };

  const clearAutoplay = () => {
    if (autoplayTimer !== undefined) {
      window.clearTimeout(autoplayTimer);
      autoplayTimer = undefined;
    }
  };

  const scheduleAutoplay = () => {
    clearAutoplay();
    if (document.visibilityState !== "visible" || prefersReducedMotion.matches) return;
    autoplayTimer = window.setTimeout(() => {
      const targetIndex = (activeIndex + 1) % chapters.length;
      setActive(targetIndex, { wrap: true, resetAutoplay: false });
      scheduleAutoplay();
    }, autoplayDelay);
  };

  const fitStoryHeadings = () => {
    headingFitFrame = undefined;
    chapters.forEach((chapter) => {
      const heading = chapter.querySelector<HTMLElement>(".story-chapter__copy h2");
      if (!heading) return;

      heading.style.removeProperty("font-size");
      const baseFontSize = Number.parseFloat(getComputedStyle(heading).fontSize);
      const availableWidth = heading.clientWidth;
      const contentWidth = heading.scrollWidth;
      if (!baseFontSize || !availableWidth || contentWidth <= availableWidth + 1) return;

      const minimumFontSize = window.innerWidth <= 480 ? 15 : 22;
      const fittedFontSize = Math.max(minimumFontSize, baseFontSize * (availableWidth / contentWidth));
      heading.style.fontSize = `${fittedFontSize}px`;
    });
  };

  const scheduleHeadingFit = () => {
    if (headingFitFrame !== undefined) window.cancelAnimationFrame(headingFitFrame);
    headingFitFrame = window.requestAnimationFrame(fitStoryHeadings);
  };

  const setActive = (nextIndex: number, options: { wrap?: boolean; resetAutoplay?: boolean } = {}) => {
    const targetIndex = options.wrap
      ? (nextIndex + chapters.length) % chapters.length
      : Math.max(0, Math.min(chapters.length - 1, nextIndex));
    if (targetIndex === activeIndex || locked) {
      if (options.resetAutoplay !== false) scheduleAutoplay();
      return;
    }

    locked = true;
    const direction = targetIndex > activeIndex ? 1 : -1;
    const previousIndex = activeIndex;
    chapters.forEach((chapter, index) => {
      chapter.classList.remove("is-active", "is-before", "is-after");
      if (index === previousIndex) chapter.classList.add(direction > 0 ? "is-before" : "is-after");
    });
    chapters[targetIndex].classList.add("is-active");
    dots.forEach((dot, index) => dot.classList.toggle("is-active", index === targetIndex));
    activeIndex = targetIndex;
    window.history.replaceState(null, "", `#${chapters[targetIndex].id}`);
    if (options.resetAutoplay !== false) scheduleAutoplay();

    window.setTimeout(() => {
      chapters.forEach((chapter, index) => {
        if (index !== activeIndex) chapter.classList.remove("is-before", "is-after");
      });
      locked = false;
    }, 760);
  };

  const onWheel = (event: WheelEvent) => {
    if (Math.abs(event.deltaY) < 8) return;
    event.preventDefault();
    scheduleAutoplay();
    setActive(activeIndex + Math.sign(event.deltaY));
  };

  const onKeyDown = (event: KeyboardEvent) => {
    const forward = ["ArrowDown", "PageDown", "ArrowRight", " "].includes(event.key);
    const backward = ["ArrowUp", "PageUp", "ArrowLeft"].includes(event.key);
    if (!forward && !backward) return;
    event.preventDefault();
    scheduleAutoplay();
    setActive(activeIndex + (forward ? 1 : -1));
  };

  const onTouchStart = (event: TouchEvent) => {
    touchStartY = event.touches[0]?.clientY ?? 0;
  };

  const onTouchEnd = (event: TouchEvent) => {
    const touchEndY = event.changedTouches[0]?.clientY ?? touchStartY;
    const distance = touchStartY - touchEndY;
    if (Math.abs(distance) > 35) {
      scheduleAutoplay();
      setActive(activeIndex + Math.sign(distance));
    }
  };

  const onDotClick = (event: MouseEvent) => {
    event.preventDefault();
    const dot = event.currentTarget as HTMLAnchorElement;
    const targetIndex = dots.indexOf(dot);
    if (targetIndex >= 0) {
      scheduleAutoplay();
      setActive(targetIndex);
    }
  };

  const onVisibilityChange = () => {
    if (document.visibilityState === "visible") scheduleAutoplay();
    else clearAutoplay();
  };

  chapters.forEach((chapter, index) => chapter.classList.toggle("is-active", index === activeIndex));
  dots.forEach((dot, index) => {
    dot.classList.toggle("is-active", index === activeIndex);
    dot.addEventListener("click", onDotClick);
  });
  window.addEventListener("wheel", onWheel, { passive: false });
  window.addEventListener("keydown", onKeyDown);
  window.addEventListener("touchstart", onTouchStart, { passive: true });
  window.addEventListener("touchend", onTouchEnd, { passive: true });
  document.addEventListener("visibilitychange", onVisibilityChange);
  prefersReducedMotion.addEventListener("change", onReducedMotionChange);
  window.addEventListener("resize", scheduleHeadingFit);
  scheduleHeadingFit();
  scheduleAutoplay();

  cleanupStoryExperience = () => {
    clearAutoplay();
    document.body.classList.remove("story-mode");
    window.removeEventListener("wheel", onWheel);
    window.removeEventListener("keydown", onKeyDown);
    window.removeEventListener("touchstart", onTouchStart);
    window.removeEventListener("touchend", onTouchEnd);
    document.removeEventListener("visibilitychange", onVisibilityChange);
    prefersReducedMotion.removeEventListener("change", onReducedMotionChange);
    window.removeEventListener("resize", scheduleHeadingFit);
    if (headingFitFrame !== undefined) window.cancelAnimationFrame(headingFitFrame);
    chapters.forEach((chapter) => {
      chapter.querySelector<HTMLElement>(".story-chapter__copy h2")?.style.removeProperty("font-size");
    });
    dots.forEach((dot) => dot.removeEventListener("click", onDotClick));
  };
}

export default {
  ...DefaultTheme,
  enhanceApp(ctx) {
    DefaultTheme.enhanceApp?.(ctx);
    const { router } = ctx;
    if (typeof window === "undefined") return;

    router.onAfterRouteChange = async () => {
      await nextTick();
      setupHomeExperience();
      setupStoryExperience();
    };
    nextTick(() => {
      setupHomeExperience();
      setupStoryExperience();
      window.setTimeout(() => {
        setupHomeExperience();
        setupStoryExperience();
      }, 120);
    });
  },
};
