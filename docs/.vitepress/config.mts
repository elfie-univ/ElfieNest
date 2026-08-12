import { defineConfig } from "vitepress";

const configuredBase = process.env.DOCS_BASE ?? "/";
const base = configuredBase.endsWith("/") ? configuredBase : `${configuredBase}/`;

export default defineConfig({
  title: "ElfieNest",
  description: "An Earth station that connects unknown life — and a home for your Elfie.",
  srcExclude: [".internal/**"],
  base,
  cleanUrls: true,
  lastUpdated: true,
  head: [
    ["link", { rel: "icon", type: "image/x-icon", href: "/assets/favicon.ico" }]
  ],
  transformHtml: (html) =>
    html.replaceAll('rel="preload stylesheet"', 'rel="stylesheet"'),
  locales: {
    // English is the site root (default).
    root: {
      label: "English",
      lang: "en",
      themeConfig: {
        logo: "/assets/elfienest-full-logo-transparent.png",
        siteTitle: false,
        nav: [
          { text: "Home", link: "/" },
          { text: "World & Story", link: "/story/" },
          { text: "Getting Started", link: "/getting-started/" },
          { text: "Developer Docs", link: "/developer/" }
        ],
        sidebar: {
          "/story/": [
            {
              text: "World & Story",
              items: [{ text: "Story prologue", link: "/story/" }]
            }
          ],
          "/getting-started/": [
            {
              text: "Getting Started",
              items: [
                { text: "User manual overview", link: "/getting-started/" },
                { text: "Install & environment", link: "/getting-started/install" },
                { text: "Configure models & data", link: "/getting-started/configuration" },
                { text: "Run your first Nest", link: "/getting-started/run" },
                { text: "Troubleshooting", link: "/getting-started/troubleshooting" },
                { text: "FAQ", link: "/getting-started/faq" }
              ]
            }
          ],
          "/developer/": [
            {
              text: "Project overview",
              items: [{ text: "Developer Docs", link: "/developer/" }]
            },
            {
              text: "Architecture",
              items: [
                { text: "Current architecture", link: "/developer/architecture/" },
                { text: "Module boundaries", link: "/developer/architecture/module-boundaries" },
                { text: "Cognitive information flow", link: "/developer/architecture/cognitive-flow" },
                { text: "Runtime & data", link: "/developer/architecture/runtime" }
              ]
            },
            {
              text: "Contracts & governance",
              items: [
                { text: "Architecture contracts", link: "/developer/contracts/" },
                { text: "Repository governance", link: "/developer/contracts/repository-governance" },
                { text: "System architecture contract", link: "/developer/contracts/system" },
                { text: "Elfie internal contract", link: "/developer/contracts/elfie" },
                { text: "Application contract", link: "/developer/contracts/application" },
                { text: "Model, Food and tool behavior", link: "/developer/contracts/model-food-tool-behavior" },
                { text: "System architecture conformance", link: "/developer/conformance/system" },
                { text: "Elfie architecture conformance", link: "/developer/conformance/elfie" },
                { text: "Application conformance", link: "/developer/conformance/application" },
                { text: "Model/Food/Tool conformance", link: "/developer/conformance/model-food-tool-conformance" },
                { text: "Architecture decisions", link: "/developer/decisions/" },
                { text: "App Ports & Adapters decision", link: "/developer/decisions/0001-lightweight-ports-adapters" },
                { text: "System Ports & Adapters decision", link: "/developer/decisions/0002-system-ports-adapters" },
                { text: "Elfie Ports & Adapters decision", link: "/developer/decisions/0005-elfie-internal-ports-adapters" }
              ]
            },
            {
              text: "Development flow",
              items: [
                { text: "Development flow", link: "/developer/development" },
                { text: "Testing & quality", link: "/developer/testing" },
                { text: "Debugging & workbenches", link: "/developer/debugging" }
              ]
            },
            {
              text: "Tooling & release",
              items: [
                { text: "Command reference", link: "/developer/tooling" },
                { text: "Developer Tools", link: "/developer/devtools" },
                { text: "Godot", link: "/developer/godot" },
                { text: "Desktop", link: "/developer/desktop" },
                { text: "Build & release", link: "/developer/build-release" }
              ]
            },
            {
              text: "Collaboration rules",
              items: [
                { text: "Code standards & constraints", link: "/developer/standards" },
                { text: "Security & data boundary", link: "/developer/security-data" }
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
      themeConfig: {
        logo: "/assets/elfienest-full-logo-transparent.png",
        siteTitle: false,
        nav: [
          { text: "首页", link: "/zh/" },
          { text: "世界观与故事", link: "/zh/story/" },
          { text: "开始使用", link: "/zh/getting-started/" },
          { text: "开发者文档", link: "/zh/developer/" }
        ],
        sidebar: {
          "/zh/story/": [
            {
              text: "世界观与故事",
              items: [{ text: "故事序章", link: "/zh/story/" }]
            }
          ],
          "/zh/getting-started/": [
            {
              text: "开始使用",
              items: [
                { text: "使用手册总览", link: "/zh/getting-started/" },
                { text: "安装与环境", link: "/zh/getting-started/install" },
                { text: "配置模型与数据", link: "/zh/getting-started/configuration" },
                { text: "运行第一座 Nest", link: "/zh/getting-started/run" },
                { text: "故障排查", link: "/zh/getting-started/troubleshooting" },
                { text: "常见问题", link: "/zh/getting-started/faq" }
              ]
            }
          ],
          "/zh/developer/": [
            {
              text: "项目总览",
              items: [{ text: "开发者文档", link: "/zh/developer/" }]
            },
            {
              text: "架构",
              items: [
                { text: "当前架构", link: "/zh/developer/architecture/" },
                { text: "模块边界", link: "/zh/developer/architecture/module-boundaries" },
                { text: "认知信息流", link: "/zh/developer/architecture/cognitive-flow" },
                { text: "运行时与数据", link: "/zh/developer/architecture/runtime" }
              ]
            },
            {
              text: "契约与治理",
              items: [
                { text: "架构契约", link: "/zh/developer/contracts/" },
                { text: "仓库架构治理", link: "/zh/developer/contracts/repository-governance" },
                { text: "系统架构契约", link: "/zh/developer/contracts/system" },
                { text: "Elfie 内部架构契约", link: "/zh/developer/contracts/elfie" },
                { text: "应用架构契约", link: "/zh/developer/contracts/application" },
                { text: "模型、Food 与工具行为", link: "/zh/developer/contracts/model-food-tool-behavior" },
                { text: "系统架构一致性", link: "/zh/developer/conformance/system" },
                { text: "Elfie 内部架构一致性", link: "/zh/developer/conformance/elfie" },
                { text: "应用架构一致性", link: "/zh/developer/conformance/application" },
                { text: "Model/Food/Tool 一致性", link: "/zh/developer/conformance/model-food-tool-conformance" },
                { text: "架构决策", link: "/zh/developer/decisions/" },
                { text: "App Ports/Adapters 决策", link: "/zh/developer/decisions/0001-lightweight-ports-adapters" },
                { text: "系统 Ports/Adapters 决策", link: "/zh/developer/decisions/0002-system-ports-adapters" },
                { text: "Elfie Ports/Adapters 决策", link: "/zh/developer/decisions/0005-elfie-internal-ports-adapters" }
              ]
            },
            {
              text: "开发流程",
              items: [
                { text: "开发流程", link: "/zh/developer/development" },
                { text: "测试与质量", link: "/zh/developer/testing" },
                { text: "调试与实验台", link: "/zh/developer/debugging" }
              ]
            },
            {
              text: "工具与发布",
              items: [
                { text: "命令参考", link: "/zh/developer/tooling" },
                { text: "Developer Tools", link: "/zh/developer/devtools" },
                { text: "Godot", link: "/zh/developer/godot" },
                { text: "Desktop", link: "/zh/developer/desktop" },
                { text: "构建与发布", link: "/zh/developer/build-release" }
              ]
            },
            {
              text: "协作规则",
              items: [
                { text: "代码规范与约束", link: "/zh/developer/standards" },
                { text: "安全与数据边界", link: "/zh/developer/security-data" }
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
