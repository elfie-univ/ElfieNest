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
          items: [{ text: "开始使用 ElfieNest", link: "/getting-started/" }]
        }
      ],
      "/developer/": [
        {
          text: "开发者文档",
          items: [
            { text: "开发者入口", link: "/developer/" },
            { text: "当前架构", link: "/developer/architecture" },
            { text: "开发流程", link: "/developer/development" },
            { text: "命令与开发工具", link: "/developer/tooling" }
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
      message: "ElfieNest 是一个仍在早期开发中的开源项目。",
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
