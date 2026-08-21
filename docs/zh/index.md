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
    <h2 id="home-download-title">把 Elfie 领回家</h2>
    <details class="home-download__notice" data-home-macos-notice hidden>
      <summary>macOS 首次安装提示：Beta 版可能被系统拦截，点击查看步骤</summary>
      <div class="home-download__notice-body">
        <p>当前 Beta 版尚未完成 Apple 签名与公证，macOS 可能会阻止安装。</p>
        <ol>
          <li>先双击下载的 <code>ElfieNest-...pkg</code>；出现拦截提示后关闭窗口。</li>
          <li>打开「<strong>系统设置</strong>」→「<strong>隐私与安全性</strong>」。</li>
          <li>在「<strong>安全性</strong>」区域找到 ElfieNest，点击「<strong>仍要打开</strong>」。</li>
          <li>再确认「<strong>打开</strong>」，输入 Mac 登录密码。</li>
        </ol>
        <p>如果没有看到「<strong>仍要打开</strong>」，请回到下载文件夹，按住 Control 点击安装包，选择「<strong>打开</strong>」，然后重新查看「<strong>隐私与安全性</strong>」。</p>
        <p class="home-download__notice-warning">请只从官方 <a href="https://github.com/elfie-univ/ElfieNest/releases" target="_blank" rel="noreferrer noopener">GitHub Release</a> 下载；如果系统提示「将损坏电脑」或检测到恶意软件，请不要继续安装。</p>
        <p class="home-download__notice-help"><a href="https://support.apple.com/guide/mac-help/open-a-mac-app-from-an-unknown-developer-mh40616/mac" target="_blank" rel="noreferrer noopener">Apple 官方说明</a></p>
      </div>
    </details>
    <a class="home-download__button" data-home-download-link href="https://github.com/elfie-univ/ElfieNest/releases" aria-label="下载 ElfieNest">
      <span class="home-download__button-icon" aria-hidden="true">↓</span>
      <span data-home-download-label>下载 ElfieNest</span>
    </a>
    <div class="home-download__meta" aria-label="已识别的平台与版本信息" aria-live="polite">
      <span class="home-download__platform">
        <span class="home-download__platform-icon home-download__platform-icon--mac" data-home-platform-icon aria-hidden="true"></span>
        <strong data-home-platform-name>macOS · Apple Silicon</strong>
      </span>
      <span data-home-release>正在查找最新版本…</span>
      <span data-home-package>包大小 —</span>
    </div>
    <div class="home-download__selector" data-home-platform-picker>
      <span class="sr-only" id="home-platform-picker-label">选择其他平台</span>
      <button class="home-download__select" data-home-platform-trigger type="button" aria-haspopup="listbox" aria-expanded="false" aria-controls="home-platform-options" aria-label="选择下载平台">
        <span class="home-download__platform-icon home-download__platform-icon--mac" data-home-platform-icon aria-hidden="true"></span>
        <span data-home-platform-trigger-name>Windows、macOS、Linux 和其他版本</span>
        <span class="home-download__select-chevron" aria-hidden="true">⌄</span>
      </button>
      <div class="home-download__menu" id="home-platform-options" data-home-platform-menu role="listbox" tabindex="-1" aria-label="可用平台" hidden>
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
    <h2 id="home-contribute-title">一个在开放中成长的家</h2>
    <p>ElfieNest 是一个本地优先的开源项目。你可以了解它如何运行、验证改动，也可以一起建造连接两个世界的桥。</p>
    <div class="home-contribute__stats" aria-label="项目社区统计">
      <div class="home-contribute__stat"><strong>—</strong><span>贡献者</span></div>
      <div class="home-contribute__stat"><strong>—</strong><span>星标</span></div>
      <div class="home-contribute__stat"><strong>—</strong><span>开放问题</span></div>
    </div>
    <div class="home-contribute__actions">
      <a class="home-button home-button--primary" href="./developer/">阅读开发者文档</a>
      <a class="home-button home-button--secondary" href="https://github.com/elfie-univ/ElfieNest">查看 GitHub</a>
    </div>
  </div>
</section>
