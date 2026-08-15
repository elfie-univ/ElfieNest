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
    <a class="home-download__button" href="https://github.com/elfie-univ/ElfieNest/releases/latest">
      <span class="home-download__button-icon" aria-hidden="true">↓</span>
      <span>Download ElfieNest</span>
    </a>
    <div class="home-download__meta" aria-label="Detected platform and build information">
      <span class="home-download__platform">
        <span class="home-download__platform-icon" data-home-platform-icon aria-hidden="true"></span>
        <strong data-home-platform-name>macOS · Apple Silicon</strong>
      </span>
      <span data-home-release>Current build</span>
      <span data-home-package>Package size —</span>
    </div>
    <label class="home-download__selector">
      <span class="sr-only">Choose another platform</span>
      <select class="home-download__select" data-home-platform-select>
        <option value="macos-arm" data-icon="" data-label="macOS · Apple Silicon">&nbsp; macOS · Apple Silicon</option>
        <option value="macos-intel" data-icon="" data-label="macOS · Intel">&nbsp; macOS · Intel</option>
        <option value="windows" data-icon="⊞" data-label="Windows · x64">⊞&nbsp; Windows · x64</option>
        <option value="linux" data-icon="◈" data-label="Linux · x64">◈&nbsp; Linux · x64</option>
      </select>
    </label>
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
