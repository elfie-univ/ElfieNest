import { defineConfig } from "vitepress";

const configuredBase = process.env.DOCS_BASE ?? "/";
const base = configuredBase.endsWith("/") ? configuredBase : `${configuredBase}/`;
const configuredSiteUrl = process.env.DOCS_SITE_URL ?? "https://elfie-univ.github.io/ElfieNest/";
const siteUrl = configuredSiteUrl.endsWith("/") ? configuredSiteUrl : `${configuredSiteUrl}/`;
const siteOrigin = new URL(siteUrl).origin;

function routePath(relativePath: string) {
  const route = relativePath
    .replaceAll("\\", "/")
    .replace(/\.md$/, "")
    .replace(/(^|\/)index$/, "")
    .replace(/^\/+|\/+$/g, "");

  return route ? `/${route}/` : "/";
}

function withBasePath(path: string) {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  if (base === "/") return normalizedPath;
  const basePath = base.replace(/\/+$/, "");
  return normalizedPath === "/" ? `${basePath}/` : `${basePath}${normalizedPath}`;
}

export default defineConfig({
  title: "ElfieNest",
  description: "An Earth station that connects unknown life — and a home for your Elfie.",
  srcExclude: [".internal/**", "**/AGENTS.md"],
  base,
  cleanUrls: true,
  lastUpdated: true,
  head: [
    ["link", { rel: "icon", type: "image/x-icon", href: `${base}assets/favicon.ico` }],
    ["link", { rel: "manifest", href: `${base}manifest.webmanifest` }],
    ["link", { rel: "apple-touch-icon", href: `${base}assets/elfienest-app-icon.png` }],
    ["meta", { name: "theme-color", content: "#050a1d" }]
  ],
  transformHead: ({ pageData, title, description }) => {
    const canonical = new URL(routePath(pageData.relativePath).replace(/^\/+/, ""), siteUrl).toString();
    const isChinese = pageData.relativePath.replaceAll("\\", "/").startsWith("zh/");
    const image = new URL("assets/elfienest-home-v2.png", siteUrl).toString();

    return [
      ["link", { rel: "canonical", href: canonical }],
      ["meta", { property: "og:type", content: "website" }],
      ["meta", { property: "og:site_name", content: "ElfieNest" }],
      ["meta", { property: "og:title", content: title }],
      ["meta", { property: "og:description", content: description }],
      ["meta", { property: "og:url", content: canonical }],
      ["meta", { property: "og:image", content: image }],
      ["meta", { property: "og:locale", content: isChinese ? "zh_CN" : "en_US" }],
      ["meta", { name: "twitter:card", content: "summary_large_image" }],
      ["meta", { name: "twitter:title", content: title }],
      ["meta", { name: "twitter:description", content: description }],
      ["meta", { name: "twitter:image", content: image }]
    ];
  },
  transformHtml: (html) => html.replaceAll('rel="preload stylesheet"', 'rel="stylesheet"'),
  sitemap: {
    hostname: siteOrigin,
    transformItems: (items) =>
      items.map((item) => ({
        ...item,
        url: withBasePath(item.url),
        links: item.links?.map((link) => ({ ...link, url: withBasePath(link.url) }))
      }))
  },
  locales: {
    // English is the site root (default).
    root: {
      label: "English",
      lang: "en",
      description: "An Earth station that connects unknown life — and a home for your Elfie.",
      themeConfig: {
        logo: { src: "/assets/elfienest-full-logo-transparent.png", alt: "ElfieNest" },
        siteTitle: false,
        nav: [
          { text: "Home", link: "/" },
          { text: "Story", link: "/story/" },
          { text: "User Guide", link: "/user-guide/" },
          { text: "Developer Docs", link: "/developer/" }
        ],
        sidebar: {
          "/story/": [
            {
              text: "Story",
              items: [{ text: "Story prologue", link: "/story/" }]
            }
          ],
          "/user-guide/": [
            {
              text: "User Guide",
              items: [
                { text: "User manual overview", link: "/user-guide/" },
                { text: "Install and configure", link: "/user-guide/install" },
                { text: "First-time configuration", link: "/user-guide/configuration" },
                { text: "Core configuration", link: "/user-guide/ready" },
                { text: "Adopt your first Elfie", link: "/user-guide/adoption" },
                { text: "Daily use: chat and phone", link: "/user-guide/run" },
                { text: "Management and Monitor", link: "/user-guide/manage" },
                { text: "Troubleshooting", link: "/user-guide/troubleshooting" },
                { text: "FAQ", link: "/user-guide/faq" }
              ]
            }
          ],
          "/developer/": [
            {
              text: "Current architecture",
              items: [
                { text: "Developer Docs", link: "/developer/" },
                { text: "Current architecture", link: "/developer/architecture/" },
                { text: "Module boundaries", link: "/developer/architecture/module-boundaries" },
                { text: "Cognitive information flow", link: "/developer/architecture/cognitive-flow" },
                { text: "Communication channels", link: "/developer/architecture/communication" },
                { text: "Runtime & data", link: "/developer/architecture/runtime" }
              ]
            },
            {
              text: "Design & governance",
              items: [
                {
                  text: "Designs",
                  collapsed: true,
                  items: [
                    { text: "Designs overview", link: "/developer/designs/" },
                    { text: "Elfie top-level module design", link: "/developer/designs/elfie-top-level-module-design" },
                    { text: "Elfie Brain ten-system architecture", link: "/developer/designs/elfie-brain-ten-system-architecture" },
                    { text: "Provider and endpoint-model availability", link: "/developer/designs/provider-model-availability" }
                  ]
                },
                {
                  text: "Contracts",
                  collapsed: true,
                  items: [
                    { text: "Architecture contracts", link: "/developer/contracts/" },
                    { text: "Repository governance", link: "/developer/contracts/repository-governance" },
                    { text: "Documentation structure contract", link: "/developer/contracts/documentation-structure" },
                    { text: "System architecture contract", link: "/developer/contracts/system" },
                    { text: "Elfie internal contract", link: "/developer/contracts/elfie" },
                    { text: "Elfie Brain internal contract", link: "/developer/contracts/brain" },
                    { text: "Application contract", link: "/developer/contracts/application" },
                    { text: "Model, Food and tool behavior", link: "/developer/contracts/model-food-tool-behavior" }
                  ]
                },
                {
                  text: "Conformance",
                  collapsed: true,
                  items: [
                    { text: "Conformance overview", link: "/developer/conformance/" },
                    { text: "Elfie architecture conformance", link: "/developer/conformance/elfie" }
                  ]
                },
                {
                  text: "Decisions (ADRs)",
                  collapsed: true,
                  items: [
                    { text: "Architecture decisions (ADRs)", link: "/developer/decisions/" },
                    { text: "App Ports & Adapters decision", link: "/developer/decisions/0001-lightweight-ports-adapters" },
                    { text: "System Ports & Adapters decision", link: "/developer/decisions/0002-system-ports-adapters" },
                    { text: "Elfie Ports & Adapters decision", link: "/developer/decisions/0005-elfie-internal-ports-adapters" },
                    { text: "Elfie life-system ownership", link: "/developer/decisions/0006-elfie-life-system-ownership" },
                    { text: "Brain ownership decision", link: "/developer/decisions/0007-brain-turn-state-and-activity-ownership" },
                    { text: "Documentation structure decision", link: "/developer/decisions/0008-documentation-information-architecture" },
                    { text: "Zero-debt closure decision", link: "/developer/decisions/0009-zero-debt-governance-closure" }
                  ]
                }
              ]
            },
            {
              text: "Engineering",
              collapsed: true,
              items: [
                { text: "Repository quality governance", link: "/developer/engineering/quality-governance" },
                { text: "Development flow", link: "/developer/engineering/development" },
                { text: "Testing & quality", link: "/developer/engineering/testing" },
                { text: "Debugging & workbenches", link: "/developer/engineering/debugging" },
                { text: "Command reference", link: "/developer/engineering/tooling" },
                { text: "Developer Tools", link: "/developer/engineering/devtools" },
                { text: "Godot", link: "/developer/engineering/godot" },
                { text: "Desktop", link: "/developer/engineering/desktop" },
                { text: "Code standards & constraints", link: "/developer/engineering/standards" },
                { text: "Security & data boundary", link: "/developer/engineering/security-data" },
                { text: "Build & release", link: "/developer/engineering/build-release" }
              ]
            }
          ]
        },
        footer: {
          message: "ElfieNest · A private Earth station connecting two worlds.",
          copyright: "Copyright © 2026 ElfieNest"
        },
        editLink: {
          pattern: "https://github.com/elfie-univ/ElfieNest/edit/main/docs/:path",
          text: "Edit this page on GitHub"
        },
        lastUpdated: {
          text: "Last updated"
        },
        outline: {
          label: "On this page"
        },
        docFooter: {
          prev: "Previous",
          next: "Next"
        }
      }
    },
    // Simplified Chinese lives under /zh/.
    zh: {
      label: "简体中文",
      lang: "zh-CN",
      link: "/zh/",
      description: "一座连接未知生命的地球基站，也是与你的 Elfie 长期陪伴的开始。",
      themeConfig: {
        logo: { src: "/assets/elfienest-full-logo-transparent.png", alt: "ElfieNest" },
        siteTitle: false,
        nav: [
          { text: "首页", link: "/zh/" },
          { text: "故事", link: "/zh/story/" },
          { text: "用户指南", link: "/zh/user-guide/" },
          { text: "开发者文档", link: "/zh/developer/" }
        ],
        sidebar: {
          "/zh/story/": [
            {
              text: "故事",
              items: [{ text: "故事序章", link: "/zh/story/" }]
            }
          ],
          "/zh/user-guide/": [
            {
              text: "用户指南",
              items: [
                { text: "使用手册总览", link: "/zh/user-guide/" },
                { text: "安装配置", link: "/zh/user-guide/install" },
                { text: "首次配置", link: "/zh/user-guide/configuration" },
                { text: "核心配置", link: "/zh/user-guide/ready" },
                { text: "领养第一只 Elfie", link: "/zh/user-guide/adoption" },
                { text: "日常使用：聊天与手机", link: "/zh/user-guide/run" },
                { text: "管理台与房间监控", link: "/zh/user-guide/manage" },
                { text: "故障排查", link: "/zh/user-guide/troubleshooting" },
                { text: "常见问题", link: "/zh/user-guide/faq" }
              ]
            }
          ],
          "/zh/developer/": [
            {
              text: "当前架构",
              items: [
                { text: "开发者文档", link: "/zh/developer/" },
                { text: "当前架构", link: "/zh/developer/architecture/" },
                { text: "模块边界", link: "/zh/developer/architecture/module-boundaries" },
                { text: "认知信息流", link: "/zh/developer/architecture/cognitive-flow" },
                { text: "通信渠道", link: "/zh/developer/architecture/communication" },
                { text: "运行时与数据", link: "/zh/developer/architecture/runtime" }
              ]
            },
            {
              text: "设计与治理",
              items: [
                {
                  text: "设计文档",
                  collapsed: true,
                  items: [
                    { text: "设计文档总览", link: "/zh/developer/designs/" },
                    { text: "Elfie 顶级模块设计", link: "/zh/developer/designs/elfie-top-level-module-design" },
                    { text: "Elfie 大脑十系统架构", link: "/zh/developer/designs/elfie-brain-ten-system-architecture" },
                    { text: "Provider 与 Endpoint 模型可用性", link: "/zh/developer/designs/provider-model-availability" }
                  ]
                },
                {
                  text: "架构契约",
                  collapsed: true,
                  items: [
                    { text: "架构契约总览", link: "/zh/developer/contracts/" },
                    { text: "仓库架构治理", link: "/zh/developer/contracts/repository-governance" },
                    { text: "文档结构契约", link: "/zh/developer/contracts/documentation-structure" },
                    { text: "系统架构契约", link: "/zh/developer/contracts/system" },
                    { text: "Elfie 内部架构契约", link: "/zh/developer/contracts/elfie" },
                    { text: "Elfie Brain 内部架构契约", link: "/zh/developer/contracts/brain" },
                    { text: "应用架构契约", link: "/zh/developer/contracts/application" },
                    { text: "模型、Food 与工具行为", link: "/zh/developer/contracts/model-food-tool-behavior" }
                  ]
                },
                {
                  text: "架构一致性",
                  collapsed: true,
                  items: [
                    { text: "架构一致性总览", link: "/zh/developer/conformance/" },
                    { text: "Elfie 内部架构一致性", link: "/zh/developer/conformance/elfie" }
                  ]
                },
                {
                  text: "架构决策记录（ADR）",
                  collapsed: true,
                  items: [
                    { text: "架构决策记录总览", link: "/zh/developer/decisions/" },
                    { text: "App Ports/Adapters 决策", link: "/zh/developer/decisions/0001-lightweight-ports-adapters" },
                    { text: "系统 Ports/Adapters 决策", link: "/zh/developer/decisions/0002-system-ports-adapters" },
                    { text: "Elfie Ports/Adapters 决策", link: "/zh/developer/decisions/0005-elfie-internal-ports-adapters" },
                    { text: "Elfie 生命系统所有权", link: "/zh/developer/decisions/0006-elfie-life-system-ownership" },
                    { text: "Brain 所有权决策", link: "/zh/developer/decisions/0007-brain-turn-state-and-activity-ownership" },
                    { text: "文档结构决策", link: "/zh/developer/decisions/0008-documentation-information-architecture" },
                    { text: "零债务收口决策", link: "/zh/developer/decisions/0009-zero-debt-governance-closure" }
                  ]
                }
              ]
            },
            {
              text: "工程实践",
              collapsed: true,
              items: [
                { text: "仓库质量治理", link: "/zh/developer/engineering/quality-governance" },
                { text: "开发流程", link: "/zh/developer/engineering/development" },
                { text: "测试与质量", link: "/zh/developer/engineering/testing" },
                { text: "调试与实验台", link: "/zh/developer/engineering/debugging" },
                { text: "命令参考", link: "/zh/developer/engineering/tooling" },
                { text: "Developer Tools", link: "/zh/developer/engineering/devtools" },
                { text: "Godot", link: "/zh/developer/engineering/godot" },
                { text: "Desktop", link: "/zh/developer/engineering/desktop" },
                { text: "代码规范与约束", link: "/zh/developer/engineering/standards" },
                { text: "安全与数据边界", link: "/zh/developer/engineering/security-data" },
                { text: "构建与发布", link: "/zh/developer/engineering/build-release" }
              ]
            }
          ]
        },
        footer: {
          message: "ElfieNest · 一座连接两个世界的私人地球基站。",
          copyright: "Copyright © 2026 ElfieNest"
        },
        editLink: {
          pattern: "https://github.com/elfie-univ/ElfieNest/edit/main/docs/:path",
          text: "在 GitHub 上编辑此页"
        },
        lastUpdated: {
          text: "最后更新"
        },
        outline: {
          label: "本页内容"
        },
        docFooter: {
          prev: "上一页",
          next: "下一页"
        }
      }
    }
  },
  themeConfig: {
    search: {
      provider: "local"
    },
    socialLinks: [
      { icon: "github", link: "https://github.com/elfie-univ/ElfieNest" }
    ]
  }
});
