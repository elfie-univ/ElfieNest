---
layout: home

hero:
  name: ElfieNest
  text: Build a home for your Elfie on your own computer
  tagline: An Earth station that connects unknown life — and the beginning of a long companionship.
  image:
    src: /assets/elfienest-home-v2.png
    alt: A person sharing a warm ElfieNest home with several Elfies
  actions:
    - theme: brand
      text: Read the story
      link: /story/
    - theme: alt
      text: Developer guide
      link: /developer/
    - theme: alt
      text: View on GitHub
      link: https://github.com/elfie-univ/ElfieNest

features:
  - title: It remembers
    details: Its experiences, relationships and growth stay with it as you spend time together.
  - title: It lives here
    details: ElfieNest gives an Elfie a body, time and space to truly live beside you.
  - title: It belongs to you
    details: It runs on your device, keeping its home and long-term memories in your hands.
---

<section class="home-download" aria-labelledby="home-download-title">
  <div class="home-download__inner">
    <h2 id="home-download-title">Bring an Elfie home</h2>
    <details class="home-download__notice" data-home-macos-notice hidden>
      <summary>macOS first-install note: the Beta build may be blocked by macOS — view steps</summary>
      <div class="home-download__notice-body">
        <p>This Beta build is not yet signed and notarized by Apple, so macOS may block the installation.</p>
        <ol>
          <li>Double-click the downloaded <code>ElfieNest-...pkg</code>. If macOS blocks it, close the warning.</li>
          <li>Open <strong>System Settings</strong> → <strong>Privacy &amp; Security</strong>.</li>
          <li>In <strong>Security</strong>, find ElfieNest and click <strong>Open Anyway</strong>.</li>
          <li>Confirm <strong>Open</strong> and enter your Mac login password.</li>
        </ol>
        <p>If <strong>Open Anyway</strong> is not shown, return to Downloads, Control-click the installer, choose <strong>Open</strong>, and check <strong>Privacy &amp; Security</strong> again.</p>
        <p class="home-download__notice-warning">Only download from the official <a href="https://github.com/elfie-univ/ElfieNest/releases" target="_blank" rel="noreferrer noopener">GitHub Releases</a>. If macOS says the app will damage your computer or detects malware, do not continue.</p>
        <p class="home-download__notice-help"><a href="https://support.apple.com/guide/mac-help/open-a-mac-app-from-an-unknown-developer-mh40616/mac" target="_blank" rel="noreferrer noopener">Apple’s official guide</a></p>
      </div>
    </details>
    <a class="home-download__button" data-home-download-link href="https://github.com/elfie-univ/ElfieNest/releases" aria-label="Download ElfieNest">
      <span class="home-download__button-icon" aria-hidden="true">↓</span>
      <span data-home-download-label>Download ElfieNest</span>
    </a>
    <div class="home-download__meta" aria-label="Detected platform and build information" aria-live="polite">
      <span class="home-download__platform">
        <span class="home-download__platform-icon home-download__platform-icon--mac" data-home-platform-icon aria-hidden="true"></span>
        <strong data-home-platform-name>macOS · Apple Silicon</strong>
      </span>
      <span data-home-release>Finding latest release…</span>
      <span data-home-package>Package size —</span>
    </div>
    <div class="home-download__selector" data-home-platform-picker>
      <span class="sr-only" id="home-platform-picker-label">Choose another platform</span>
      <button class="home-download__select" data-home-platform-trigger type="button" aria-haspopup="listbox" aria-expanded="false" aria-controls="home-platform-options" aria-label="Choose download platform">
        <span class="home-download__platform-icon home-download__platform-icon--mac" data-home-platform-icon aria-hidden="true"></span>
        <span data-home-platform-trigger-name>Windows, macOS, Linux, and other versions</span>
        <span class="home-download__select-chevron" aria-hidden="true">⌄</span>
      </button>
      <div class="home-download__menu" id="home-platform-options" data-home-platform-menu role="listbox" tabindex="-1" aria-label="Available platforms" hidden>
        <button class="home-download__option" data-home-platform-option data-platform="macos-arm" type="button" role="option" aria-selected="false">
          <span class="home-download__option-icon home-download__option-icon--mac" aria-hidden="true"></span>
          <span class="home-download__option-label"><span>macOS</span><small>Apple Silicon</small></span>
          <span class="home-download__option-size" data-home-platform-option-size>—</span>
        </button>
        <button class="home-download__option" data-home-platform-option data-platform="macos-intel" type="button" role="option" aria-selected="false">
          <span class="home-download__option-icon home-download__option-icon--mac" aria-hidden="true"></span>
          <span class="home-download__option-label"><span>macOS</span><small>Intel</small></span>
          <span class="home-download__option-size" data-home-platform-option-size>—</span>
        </button>
        <button class="home-download__option" data-home-platform-option data-platform="windows" type="button" role="option" aria-selected="false">
          <span class="home-download__option-icon home-download__option-icon--windows" aria-hidden="true">⊞</span>
          <span class="home-download__option-label"><span>Windows</span><small>x64</small></span>
          <span class="home-download__option-size" data-home-platform-option-size>—</span>
        </button>
        <button class="home-download__option" data-home-platform-option data-platform="linux" type="button" role="option" aria-selected="false">
          <span class="home-download__option-icon home-download__option-icon--linux" aria-hidden="true">◈</span>
          <span class="home-download__option-label"><span>Linux</span><small>x64 · DEB</small></span>
          <span class="home-download__option-size" data-home-platform-option-size>—</span>
        </button>
      </div>
    </div>
  </div>
</section>

<section class="home-contribute" aria-labelledby="home-contribute-title">
  <div class="home-contribute__inner">
    <h2 id="home-contribute-title">A home that grows in the open</h2>
    <p>ElfieNest is a local-first open-source project. Learn how it works, verify changes, and help build the bridge between two worlds.</p>
    <div class="home-contribute__stats" aria-label="Project community statistics">
      <div class="home-contribute__stat"><strong>—</strong><span>Contributors</span></div>
      <div class="home-contribute__stat"><strong>—</strong><span>Stars</span></div>
      <div class="home-contribute__stat"><strong>—</strong><span>Open issues</span></div>
    </div>
    <div class="home-contribute__actions">
      <a class="home-button home-button--primary" href="./developer/">Read developer docs</a>
      <a class="home-button home-button--secondary" href="https://github.com/elfie-univ/ElfieNest">View GitHub</a>
    </div>
  </div>
</section>
