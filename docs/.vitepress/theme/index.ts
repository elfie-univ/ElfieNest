import DefaultTheme from "vitepress/theme";
import { nextTick } from "vue";
import "./custom.css";

let cleanupStoryExperience: (() => void) | undefined;
let cleanupHomeExperience: (() => void) | undefined;
let homeExperiencePath: string | undefined;

type HomeDownloadPlatform = "macos-arm" | "macos-intel" | "windows" | "linux";

interface HomeDownloadDefinition {
  id: HomeDownloadPlatform;
  label: string;
  icon: string;
  iconClass: string;
}

interface HomeGithubAsset {
  name: string;
  size: number;
  browser_download_url: string;
}

interface HomeGithubRelease {
  tag_name: string;
  name?: string;
  html_url?: string;
  draft?: boolean;
  assets: HomeGithubAsset[];
}

interface HomeUserAgentData {
  platform?: string;
  architecture?: string;
  getHighEntropyValues?: (hints: string[]) => Promise<{ architecture?: string }>;
}

const HOME_RELEASES_URL = "https://github.com/elfie-univ/ElfieNest/releases";
const HOME_RELEASES_API = "https://api.github.com/repos/elfie-univ/ElfieNest/releases?per_page=20";
const HOME_DOWNLOAD_PLATFORMS: HomeDownloadDefinition[] = [
  { id: "macos-arm", label: "macOS · Apple Silicon", icon: "", iconClass: "home-download__platform-icon--mac" },
  { id: "macos-intel", label: "macOS · Intel", icon: "", iconClass: "home-download__platform-icon--mac" },
  { id: "windows", label: "Windows · x64", icon: "⊞", iconClass: "home-download__platform-icon--windows" },
  { id: "linux", label: "Linux · x64", icon: "◈", iconClass: "home-download__platform-icon--linux" }
];

function homeDownloadCopy() {
  const isChinese = document.documentElement.lang.toLowerCase().startsWith("zh") || window.location.pathname.startsWith("/zh/");
  return {
    loadingRelease: isChinese ? "正在查找最新版本…" : "Finding latest release…",
    releaseUnavailable: isChinese ? "版本信息暂不可用" : "Release info unavailable",
    packageUnavailable: isChinese ? "包大小 —" : "Package size —",
    packagePrefix: isChinese ? "包大小" : "Package size",
    download: isChinese ? "下载 ElfieNest" : "Download ElfieNest",
    loadingDownload: isChinese ? "正在准备下载…" : "Preparing download…",
    viewReleases: isChinese ? "查看发布版本" : "View releases",
    notAvailable: isChinese ? "暂不可用" : "Unavailable",
    choosePlatform: isChinese ? "选择下载平台" : "Choose download platform",
    otherPlatforms: isChinese ? "Windows、macOS、Linux 和其他版本" : "Windows, macOS, Linux, and other versions"
  };
}

function homeFormatDownloadSize(size: number) {
  if (!Number.isFinite(size) || size <= 0) return "—";
  if (size < 1_000_000_000) return `${Math.round(size / 1_000_000)} MB`;
  return `${(size / 1_000_000_000).toFixed(1)} GB`;
}

function homeAssetMatchesPlatform(asset: HomeGithubAsset, platform: HomeDownloadPlatform) {
  const name = asset.name.toLowerCase();
  if (!/\.(pkg|exe|deb)$/.test(name)) return false;

  if (platform === "macos-arm") return /(?:mac|darwin)[-_]arm64(?:[-_.]|$)/.test(name);
  if (platform === "macos-intel") return /(?:mac|darwin)[-_](?:x64|amd64)(?:[-_.]|$)/.test(name);
  if (platform === "windows") return /(?:win32|windows|win)[-_](?:x64|amd64)(?:[-_.]|$)/.test(name);
  return /linux[-_](?:x64|amd64)(?:[-_.]|$)/.test(name);
}

function homeReleaseAssets(release: HomeGithubRelease) {
  const assets = new Map<HomeDownloadPlatform, HomeGithubAsset>();
  HOME_DOWNLOAD_PLATFORMS.forEach(({ id }) => {
    const asset = release.assets.find((candidate) => homeAssetMatchesPlatform(candidate, id));
    if (asset) assets.set(id, asset);
  });
  return assets;
}

async function detectHomeDownloadPlatform(): Promise<HomeDownloadPlatform> {
  const userAgentData = (navigator as Navigator & { userAgentData?: HomeUserAgentData }).userAgentData;
  let architecture = userAgentData?.architecture ?? "";
  if (userAgentData?.getHighEntropyValues) {
    try {
      architecture = (await userAgentData.getHighEntropyValues(["architecture"])).architecture ?? architecture;
    } catch {
      // Some browsers expose the low-entropy platform only. The manual picker
      // remains available when architecture detection is not supported.
    }
  }

  const platformHint = `${userAgentData?.platform ?? ""} ${navigator.platform} ${navigator.userAgent}`.toLowerCase();
  if (platformHint.includes("win")) return "windows";
  if (platformHint.includes("linux")) return "linux";
  if (platformHint.includes("mac")) {
    const architectureHint = `${architecture} ${userAgentData?.architecture ?? ""}`.toLowerCase();
    if (/(arm|aarch|apple silicon)/.test(architectureHint)) return "macos-arm";
    if (/(x86|x64|amd64|intel)/.test(architectureHint)) return "macos-intel";
    return "macos-arm";
  }

  // Keep the existing Mac-first default for browsers that intentionally hide
  // their platform. The menu makes the other supported targets one click away.
  return "macos-arm";
}

function setupHomeDownload(download: HTMLElement) {
  const copy = homeDownloadCopy();
  const picker = download.querySelector<HTMLElement>("[data-home-platform-picker]");
  const trigger = download.querySelector<HTMLButtonElement>("[data-home-platform-trigger]");
  const menu = download.querySelector<HTMLElement>("[data-home-platform-menu]");
  const options = [...download.querySelectorAll<HTMLButtonElement>("[data-home-platform-option]")];
  const downloadLink = download.querySelector<HTMLAnchorElement>("[data-home-download-link]");
  const downloadLabel = download.querySelector<HTMLElement>("[data-home-download-label]");
  const releaseElement = download.querySelector<HTMLElement>("[data-home-release]");
  const packageElement = download.querySelector<HTMLElement>("[data-home-package]");
  const macosNotice = download.querySelector<HTMLDetailsElement>("[data-home-macos-notice]");
  const platformIcons = [...download.querySelectorAll<HTMLElement>("[data-home-platform-icon]")];
  const platformNames = [...download.querySelectorAll<HTMLElement>("[data-home-platform-name]")];
  const triggerName = download.querySelector<HTMLElement>("[data-home-platform-trigger-name]");

  if (!picker || !trigger || !menu || options.length === 0 || !downloadLink || !downloadLabel || !releaseElement || !packageElement || !triggerName) {
    return () => undefined;
  }

  const controller = new AbortController();
  let selectedPlatform: HomeDownloadPlatform = "macos-arm";
  let hasManualSelection = false;
  let releaseUrl = HOME_RELEASES_URL;
  let assets = new Map<HomeDownloadPlatform, HomeGithubAsset>();
  let releaseState: "loading" | "ready" | "unavailable" = "loading";
  let menuOpen = false;
  let hasDetectedPlatform = false;

  const definitionFor = (platform: HomeDownloadPlatform) =>
    HOME_DOWNLOAD_PLATFORMS.find((definition) => definition.id === platform) ?? HOME_DOWNLOAD_PLATFORMS[0];

  const isMacosPlatform = (platform: HomeDownloadPlatform) => platform === "macos-arm" || platform === "macos-intel";

  const updateMacosNotice = () => {
    if (!macosNotice || !hasDetectedPlatform) return;
    const isMacos = isMacosPlatform(selectedPlatform);
    macosNotice.hidden = !isMacos;
  };

  const clearMenuPosition = () => {
    ["position", "top", "right", "bottom", "left", "width", "max-height"].forEach((property) => {
      menu.style.removeProperty(property);
    });
  };

  const positionMenu = () => {
    if (!menuOpen) return;
    const triggerRect = trigger.getBoundingClientRect();
    const viewportPadding = 16;
    const gap = 10;
    const desiredHeight = Math.min(menu.scrollHeight, 420);
    const spaceAbove = triggerRect.top - gap - viewportPadding;
    const spaceBelow = window.innerHeight - triggerRect.bottom - gap - viewportPadding;
    const openAbove = spaceAbove > spaceBelow;
    const availableSpace = Math.max(96, openAbove ? spaceAbove : spaceBelow);
    const width = Math.min(triggerRect.width, Math.max(96, window.innerWidth - viewportPadding * 2));
    const left = Math.min(
      Math.max(triggerRect.left, viewportPadding),
      Math.max(viewportPadding, window.innerWidth - width - viewportPadding)
    );

    menu.style.position = "fixed";
    menu.style.left = `${left}px`;
    menu.style.right = "auto";
    menu.style.width = `${width}px`;
    menu.style.maxHeight = `${Math.min(desiredHeight, availableSpace)}px`;
    if (openAbove) {
      menu.style.top = "auto";
      menu.style.bottom = `${window.innerHeight - triggerRect.top + gap}px`;
    } else {
      menu.style.top = `${triggerRect.bottom + gap}px`;
      menu.style.bottom = "auto";
    }
  };

  const setMenuOpen = (open: boolean, focusSelected = false) => {
    menuOpen = open;
    menu.hidden = !open;
    trigger.setAttribute("aria-expanded", String(open));
    picker.classList.toggle("is-open", open);
    if (!open) {
      clearMenuPosition();
      return;
    }
    window.requestAnimationFrame(() => {
      positionMenu();
      if (!focusSelected) return;
      window.requestAnimationFrame(() => {
        options.find((option) => option.dataset.platform === selectedPlatform)?.focus();
      });
    });
  };

  const updateDownload = () => {
    const definition = definitionFor(selectedPlatform);
    const asset = assets.get(selectedPlatform);
    updateMacosNotice();
    platformNames.forEach((element) => {
      element.textContent = definition.label;
    });
    triggerName.textContent = hasManualSelection ? definition.label : copy.otherPlatforms;
    platformIcons.forEach((element) => {
      element.className = `home-download__platform-icon ${definition.iconClass}`;
      element.textContent = definition.icon;
    });
    trigger.setAttribute("aria-label", `${copy.choosePlatform}: ${definition.label}`);
    trigger.dataset.platform = selectedPlatform;

    options.forEach((option) => {
      const platform = option.dataset.platform as HomeDownloadPlatform;
      const optionAsset = assets.get(platform);
      option.setAttribute("aria-selected", String(platform === selectedPlatform));
      option.classList.toggle("is-current", platform === selectedPlatform);
      const size = option.querySelector<HTMLElement>("[data-home-platform-option-size]");
      if (size) size.textContent = optionAsset ? homeFormatDownloadSize(optionAsset.size) : releaseState === "loading" ? "—" : copy.notAvailable;
    });

    if (asset) {
      downloadLink.href = asset.browser_download_url;
      downloadLink.classList.remove("is-unavailable");
      downloadLink.removeAttribute("aria-disabled");
      downloadLabel.textContent = copy.download;
      downloadLink.setAttribute("aria-label", `${copy.download} · ${definition.label}`);
      packageElement.textContent = `${copy.packagePrefix} ${homeFormatDownloadSize(asset.size)}`;
    } else {
      downloadLink.href = releaseUrl;
      downloadLink.classList.add("is-unavailable");
      downloadLink.removeAttribute("aria-disabled");
      downloadLabel.textContent = releaseState === "loading" ? copy.loadingDownload : copy.viewReleases;
      downloadLink.setAttribute("aria-label", `${copy.viewReleases} · ${definition.label}`);
      packageElement.textContent = copy.packageUnavailable;
    }
  };

  const selectPlatform = (platform: HomeDownloadPlatform, manual = false) => {
    if (!HOME_DOWNLOAD_PLATFORMS.some((definition) => definition.id === platform)) return;
    selectedPlatform = platform;
    hasManualSelection = hasManualSelection || manual;
    updateDownload();
  };

  const onTriggerClick = () => setMenuOpen(!menuOpen, !menuOpen);
  const onOptionClick = (event: MouseEvent) => {
    const option = event.currentTarget as HTMLButtonElement;
    selectPlatform(option.dataset.platform as HomeDownloadPlatform, true);
    setMenuOpen(false);
    trigger.focus();
  };
  const onTriggerKeyDown = (event: KeyboardEvent) => {
    if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setMenuOpen(true, true);
    } else if (event.key === "Escape") {
      setMenuOpen(false);
    }
  };
  const onMenuKeyDown = (event: KeyboardEvent) => {
    const currentIndex = options.findIndex((option) => option === document.activeElement);
    if (event.key === "Escape") {
      event.preventDefault();
      setMenuOpen(false);
      trigger.focus();
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const direction = event.key === "ArrowDown" ? 1 : -1;
      const nextIndex = (currentIndex + direction + options.length) % options.length;
      options[nextIndex]?.focus();
      return;
    }
    if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      options[event.key === "Home" ? 0 : options.length - 1]?.focus();
    }
  };
  const onDocumentPointerDown = (event: PointerEvent) => {
    if (menuOpen && !picker.contains(event.target as Node)) setMenuOpen(false);
  };
  const onMenuWheel = (event: WheelEvent) => {
    if (menuOpen) event.stopPropagation();
  };
  const onViewportChange = () => {
    if (menuOpen) window.requestAnimationFrame(positionMenu);
  };

  trigger.addEventListener("click", onTriggerClick);
  trigger.addEventListener("keydown", onTriggerKeyDown);
  menu.addEventListener("keydown", onMenuKeyDown);
  menu.addEventListener("wheel", onMenuWheel);
  options.forEach((option) => option.addEventListener("click", onOptionClick));
  document.addEventListener("pointerdown", onDocumentPointerDown);
  window.addEventListener("resize", onViewportChange);
  window.addEventListener("scroll", onViewportChange, true);
  setMenuOpen(false);
  releaseElement.textContent = copy.loadingRelease;
  updateDownload();

  const loadRelease = async () => {
    try {
      const response = await fetch(HOME_RELEASES_API, {
        headers: { Accept: "application/vnd.github+json" },
        cache: "no-store",
        signal: controller.signal
      });
      if (!response.ok) throw new Error(`GitHub Releases returned ${response.status}`);
      const releases = (await response.json()) as HomeGithubRelease[];
      const release = releases.find((candidate) => !candidate.draft && candidate.assets?.some((asset) => /\.(pkg|exe|deb)$/.test(asset.name.toLowerCase())));
      if (!release) throw new Error("No published ElfieNest release with installers was found");

      releaseUrl = release.html_url ?? `${HOME_RELEASES_URL}/tag/${encodeURIComponent(release.tag_name)}`;
      assets = homeReleaseAssets(release);
      releaseState = "ready";
      releaseElement.textContent = release.tag_name;
      updateDownload();
    } catch (error) {
      if (controller.signal.aborted) return;
      console.warn("ElfieNest release metadata could not be loaded.", error);
      releaseElement.textContent = copy.releaseUnavailable;
      assets = new Map<HomeDownloadPlatform, HomeGithubAsset>();
      releaseState = "unavailable";
      updateDownload();
    }
  };

  void loadRelease();
  void detectHomeDownloadPlatform().then((platform) => {
    if (controller.signal.aborted) return;
    hasDetectedPlatform = true;
    if (!hasManualSelection) selectPlatform(platform);
    else updateMacosNotice();
  });

  return () => {
    controller.abort();
    trigger.removeEventListener("click", onTriggerClick);
    trigger.removeEventListener("keydown", onTriggerKeyDown);
    menu.removeEventListener("keydown", onMenuKeyDown);
    menu.removeEventListener("wheel", onMenuWheel);
    options.forEach((option) => option.removeEventListener("click", onOptionClick));
    document.removeEventListener("pointerdown", onDocumentPointerDown);
    window.removeEventListener("resize", onViewportChange);
    window.removeEventListener("scroll", onViewportChange, true);
    setMenuOpen(false);
  };
}

function setupHomeExperience() {
  const home = document.querySelector<HTMLElement>(".VPHome");
  if (!document.body) {
    window.setTimeout(setupHomeExperience, 80);
    return;
  }

  if (!home) {
    cleanupHomeExperience?.();
    cleanupHomeExperience = undefined;
    // The home layout is rendered asynchronously on a fresh page load. Keep
    // polling only while the route is still waiting for its home layout; a
    // normal documentation page already has VPDoc, and the story page has its
    // own marker, so neither route can leave a timer behind.
    if (!document.querySelector(".VPDoc") && !document.querySelector("[data-story-scroll]")) {
      window.setTimeout(setupHomeExperience, 80);
    }
    return;
  }

  const hero = home?.querySelector<HTMLElement>(".VPHero");
  const features = home?.querySelector<HTMLElement>(".VPHomeFeatures");
  const download = home?.querySelector<HTMLElement>(".home-download");
  const contribute = home?.querySelector<HTMLElement>(".home-contribute");

  if (!hero || !features || !download || !contribute) {
    window.setTimeout(setupHomeExperience, 80);
    return;
  }

  const heroPage = home.querySelector<HTMLElement>(".home-scroll__page--hero");
  const isReady =
    homeExperiencePath === window.location.pathname &&
    home.classList.contains("home-scroll") &&
    document.body.classList.contains("home-mode") &&
    heroPage?.contains(hero) &&
    heroPage.contains(features) &&
    download.classList.contains("home-scroll__page--download") &&
    contribute.classList.contains("home-scroll__page--community") &&
    Boolean(document.querySelector(".home-timeline"));
  if (isReady) return;

  cleanupHomeExperience?.();
  cleanupHomeExperience = undefined;

  const page = document.createElement("section");
  page.className = "home-scroll__page home-scroll__page--hero";
  page.id = "home";
  page.setAttribute("aria-label", "Home");
  home.insertBefore(page, hero);
  page.append(hero, features);

  download.classList.add("home-scroll__page", "home-scroll__page--download");
  download.id = "download";
  contribute.classList.add("home-scroll__page", "home-scroll__page--community");
  contribute.id = "community";

  const pages = [page, download, contribute];
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
    const openMenu = download.querySelector<HTMLElement>("[data-home-platform-menu]:not([hidden])");
    if (openMenu && event.target instanceof Node && download.contains(event.target)) {
      event.preventDefault();
      return;
    }
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

  const cleanupDownload = setupHomeDownload(download);
  cleanupHomeExperience = () => {
    cleanupDownload();
    observer.disconnect();
    dots.forEach((dot) => dot.removeEventListener("click", onDotClick));
    window.removeEventListener("wheel", onWheel);
    if (wheelUnlockTimer !== undefined) window.clearTimeout(wheelUnlockTimer);
    wheelUnlockTimer = undefined;
    wheelLocked = false;
    timeline.remove();
    if (page.parentElement === home) {
      home.insertBefore(hero, page);
      home.insertBefore(features, page);
    }
    page.remove();
    download.classList.remove("home-scroll__page", "home-scroll__page--download");
    contribute.classList.remove("home-scroll__page", "home-scroll__page--community");
    home.classList.remove("home-scroll");
    delete home.dataset.homeScroll;
    document.body.classList.remove("home-mode");
    homeExperiencePath = undefined;
  };
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

    const scheduleExperiences = () => {
      // Wait for VitePress/Vue hydration to finish before moving any
      // Vue-managed nodes into the immersive page shells.
      window.setTimeout(() => {
        setupHomeExperience();
        setupStoryExperience();
      }, 120);
    };

    router.onAfterRouteChange = async () => {
      await nextTick();
      scheduleExperiences();
    };
    scheduleExperiences();
  },
};
