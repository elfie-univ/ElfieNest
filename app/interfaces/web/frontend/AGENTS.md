# Web 前端目录规则

本文件只作用于 `app/interfaces/web/frontend/`。

- 新增控件或替换现有控件时，先复用 `src/components/ui/` 中现有的 shadcn/Radix
  原语和页面级复合组件，例如 `SelectField`、`TextField` 和
  `Button`。已有组件覆盖同一交互时，不在页面内重复手写原生控件。
- 共享组件确实缺失时，只补完成当前页面所必需的最小能力，不顺手迁移历史页面。
- 样式使用现有语义 token，并遵守 `DESIGN.md` 与 `DESIGN_zh.md`。
- 默认只运行受影响组件或页面的测试，以及已有的局部 lint/typecheck。全前端测试、
  全量构建和浏览器视觉 QA 仍按根目录 S/M/L 规则决定，不能自动升级。
