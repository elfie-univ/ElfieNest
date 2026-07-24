import { defineConfig } from "vitepress";

const configuredBase = process.env.DOCS_BASE ?? "/";
const base = configuredBase.endsWith("/") ? configuredBase : `${configuredBase}/`;

export default defineConfig({
  lang: "zh-CN",
  title: "ElfieNest",
  description: "为来自未知方向的生命，建立第一座地球基站。",
  base,
  cleanUrls: true,
  lastUpdated: true,
  transformHtml: (html) =>
    html.replaceAll('rel="preload stylesheet"', 'rel="stylesheet"'),
  themeConfig: {
    nav: [
      { text: "首页", link: "/" },
      { text: "世界观与故事", link: "/story/" },
      { text: "开始使用", link: "/getting-started/" },
      { text: "开发者文档", link: "/developer/" }
    ],
    sidebar: {
      "/story/": [
        {
          text: "世界观与故事",
          items: [{ text: "故事序章", link: "/story/" }]
        }
      ],
      "/getting-started/": [
        {
          text: "开始使用",
          items: [
            { text: "使用手册总览", link: "/getting-started/" },
            { text: "安装与环境", link: "/getting-started/install" },
            { text: "配置模型与数据", link: "/getting-started/configuration" },
            { text: "运行第一座 Nest", link: "/getting-started/run" },
            { text: "故障排查", link: "/getting-started/troubleshooting" },
            { text: "常见问题", link: "/getting-started/faq" }
          ]
        }
      ],
      "/developer/": [
        {
          text: "项目总览",
          items: [{ text: "开发者文档", link: "/developer/" }]
        },
        {
          text: "架构",
          items: [
            { text: "当前架构", link: "/developer/architecture" },
            { text: "模块边界", link: "/developer/architecture-boundaries" },
            { text: "认知信息流", link: "/developer/architecture-cognitive-flow" },
            { text: "运行时与数据", link: "/developer/architecture-runtime" }
          ]
        },
        {
          text: "开发流程",
          items: [
            { text: "开发流程", link: "/developer/development" },
            { text: "测试与质量", link: "/developer/testing" },
            { text: "调试与实验台", link: "/developer/debugging" }
          ]
        },
        {
          text: "工具与发布",
          items: [
            { text: "命令参考", link: "/developer/tooling" },
            { text: "Developer Tools", link: "/developer/devtools" },
            { text: "Godot", link: "/developer/godot" },
            { text: "Desktop", link: "/developer/desktop" },
            { text: "构建与发布", link: "/developer/build-release" }
          ]
        },
        {
          text: "协作规则",
          items: [
            { text: "代码规范与约束", link: "/developer/standards" },
            { text: "安全与数据边界", link: "/developer/security-data" }
          ]
        }
      ]
    },
    search: {
      provider: "local"
    },
    socialLinks: [
      { icon: "github", link: "https://github.com/elfie-univ/ElfieNest" }
    ],
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
});
