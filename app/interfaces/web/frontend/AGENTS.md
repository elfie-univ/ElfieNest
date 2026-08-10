# Web 前端目录规则

本文件只作用于 `app/interfaces/web/frontend/`。

## API 调用边界

- 产品 API 的目标契约以 `app/interfaces/api/AGENTS.md` 为权威；新增或修改调用时先
  搜索现有 API Client、Route 和 Schema，确认目标业务域、调用方权限和后端强类型
  响应，优先复用已有能力，禁止按页面自创接口。
- API 路径、请求封装和响应 Schema 只能位于 `src/api/`。页面、组件和 store 不得
  直接调用 `fetch`、`requestJson`、`ownerRead` 或硬编码 `/api/...`；当前遗留调用
  在对应业务域迁移时移入 API Client，不得继续复制。
- `src/api/` 按 `auth`、`setup`、`me`、`elfies`、`admin/*`、`observer` 等业务域
  组织，不按 Chat、Manage、Monitor 等页面名称复制客户端。
- 后端 Pydantic/OpenAPI 是 HTTP 契约权威。生成 TypeScript 客户端建立前，每个响应
  必须由严格 Zod Schema 在 API Client 边界校验；组件只接收解析后的类型。
- API Client、Schema、store 和组件之间禁止使用 `any` 传递接口数据。原始 HTTP
  响应只能在传输边界暂时使用 `unknown`，并必须立即解析；禁止用 `as SomeType`、
  双重类型断言或宽泛索引签名绕过运行时校验。
- `/elfies` 是当前主体可见精灵集合，`relationship=owned` 是“我的精灵”过滤；禁止
  新增 `/me/elfies` 或在前端自行拼出第三套精灵事实。
- 普通成员和管理员投影使用不同 Client 与类型，禁止根据角色对同一个未约束响应做
  字段猜测。错误分支使用稳定 `error.code`，不得解析中文或英文 `message`。
- 迁移旧接口时先迁移全部生产调用方，再删除旧 Client、Schema、测试夹具和路径；
  不新增 fallback 请求、双读或永久兼容别名。

- 新增控件或替换现有控件时，先复用 `src/components/ui/` 中现有的 shadcn/Radix
  原语和页面级复合组件，例如 `SelectField`、`TextField` 和
  `Button`。已有组件覆盖同一交互时，不在页面内重复手写原生控件。
- 共享组件确实缺失时，只补完成当前页面所必需的最小能力，不顺手迁移历史页面。
- 样式使用现有语义 token，并遵守 `DESIGN.md` 与 `DESIGN_zh.md`。
- 默认只运行受影响组件或页面的测试，以及已有的局部 lint/typecheck。全前端测试、
  全量构建和浏览器视觉 QA 仍按根目录 S/M/L 规则决定，不能自动升级。
