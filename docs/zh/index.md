---
layout: home

hero:
  name: ElfieNest
  text: 在你的电脑上，为你的 Elfie 建立一个家
  tagline: 一座连接未知生命的地球基站，也是一段长期陪伴关系的开始。
  image:
    src: /assets/elfienest-home-v2.png
    alt: 人与多只 Elfie 共同生活的温暖 ElfieNest
  actions:
    - theme: brand
      text: 阅读故事
      link: /zh/story/
    - theme: alt
      text: 开发者指南
      link: /zh/developer/
    - theme: alt
      text: 查看 GitHub
      link: https://github.com/elfie-univ/ElfieNest

features:
  - title: 它会记住
    details: 它的经历、关系和成长，会在一次次相处中留下来。
  - title: 它生活在这里
    details: ElfieNest 给它身体、时间和空间，让它真正生活在你身边。
  - title: 它属于你
    details: 它运行在你的设备上，家和长期记忆都由你掌握。
---

<section class="home-download" aria-labelledby="home-download-title">
  <div class="home-download__inner">
    <h2 id="home-download-title">把一个 Elfie 带回家</h2>
    <a class="home-download__button" href="https://github.com/elfie-univ/ElfieNest/releases/latest">
      <span class="home-download__button-icon" aria-hidden="true">↓</span>
      <span>下载 ElfieNest</span>
    </a>
    <div class="home-download__meta" aria-label="已识别的平台与版本信息">
      <span class="home-download__platform">
        <span class="home-download__platform-icon" data-home-platform-icon aria-hidden="true"></span>
        <strong data-home-platform-name>macOS · Apple Silicon</strong>
      </span>
      <span data-home-release>当前版本</span>
      <span data-home-package>包大小 —</span>
    </div>
    <label class="home-download__selector">
      <span class="sr-only">选择其他平台</span>
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
    <h2 id="home-contribute-title">一个在开放中成长的家</h2>
    <p>ElfieNest 是一个本地优先的开源项目。你可以了解它如何运行、验证改动，也可以一起建造连接两个世界的桥。</p>
    <div class="home-contribute__stats" aria-label="项目社区统计">
      <div class="home-contribute__stat"><strong>—</strong><span>贡献者</span></div>
      <div class="home-contribute__stat"><strong>—</strong><span>星标</span></div>
      <div class="home-contribute__stat"><strong>—</strong><span>开放问题</span></div>
    </div>
    <div class="home-contribute__actions">
      <a class="home-button home-button--primary" href="/zh/developer/">阅读开发者文档</a>
      <a class="home-button home-button--secondary" href="https://github.com/elfie-univ/ElfieNest">查看 GitHub</a>
    </div>
  </div>
</section>
