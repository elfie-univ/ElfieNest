# 构建与发布

## 构建目录

```text
build/  可再生中间构建产物，不提交
dist/   最终发行物，不提交
docs/.vitepress/dist/  VitePress 构建产物，不提交
```

Godot Web、Desktop JavaScript 和 Python Core 的生成结果必须进入对应构建目录，不
写回源码目录。

## 文档站

```bash
cd docs
npx --yes pnpm@10.12.1 install --frozen-lockfile
DOCS_BASE=/ npx --yes pnpm@10.12.1 build
```

GitHub Pages 使用 `/ElfieNest/` base。Pull Request 只构建；只有经过负责人审阅并
进入 `main` 的提交才允许进入 Pages 部署 job。

## 发布门

发布前必须确认：

1. 代码、测试和文档事实一致；
2. Gitleaks、质量基线和架构测试通过；
3. 公开页面没有私有世界观、合作材料和未审阅截图；
4. 用户完成页面目视验收；
5. 再由负责人决定何时提交、推送和部署。
