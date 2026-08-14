# ElfieNest API 目录规范

本文件只作用于 `app/interfaces/api/`，细化父级 `app/AGENTS.md` 的 HTTP 与
WebSocket 规则，并定义产品 API 的长期契约。当前用户指令和更高层
规则优先；本文件不得改变 App 的依赖方向、Port 所有权或组合根规则。

## 核心原则

- 产品 API 使用版本化、按业务资源组织的 REST 接口；实时通信使用版本化、强类型的
  WebSocket 协议。
- 新增接口前必须搜索现有 Route、前端 Client、Feature、Repository 和测试，优先
  复用已有能力；不得按页面或调用方重复建设接口。
- 同一业务能力只能有一个权威接口和一个权威 Feature 实现。Setup、聊天、管理、
  监控、移动端和外设只能读取不同权限投影，不能各自维护业务事实。
- Route 只处理协议边界，不直接执行 SQL、确定数据目录或承载业务规则。
- 每个请求体、响应和错误都必须有明确、严格、可测试的模型。
- 产品 API 默认位于 `/api/v1`。除本文件明确列出的基础设施例外外，不得新增未经
  用户批准的非 `/api/v1` 产品接口。
- 替换接口时必须同步全部真实调用方，并立即删除被替代的旧 Route、Client、DTO 和
  测试夹具；0.x 首版阶段不保留长期兼容壳、双路由、fallback read 或字段 alias。

页面路由不是 API 边界。`/`、`/setup`、`/login`、`/chat`、`/manage`、`/monitor`
和静态资源不得成为业务事实源。`/api/health` 是不带版本的进程探针例外，不得加入
业务统计或页面文案。

## 业务域与资源归属

目标顶级范围如下；它定义归属，不表示尚未实现的能力已经存在：

```text
/api/v1/auth/*
/api/v1/setup/*
/api/v1/me/*
/api/v1/elfies/*
/api/v1/admin/*
/api/v1/observer/*
/api/v1/ws/*
```

- `/auth`：登录、登出和会话认证。
- `/setup`：首次安装所需的受限投影和安装流程。
- `/me`：当前登录成员自身、个人流程和个人关系。
- `/elfies`：当前主体有权看到和操作的独立精灵资源。
- `/admin`：管理员对整套系统的全局管理投影。
- `/observer`：获授权的只读运行观测。
- `/ws`：聊天、外部身体等版本化实时协议。

移动端是客户端，不是业务域。除推送注册、设备配对等真正独有资源外，必须复用相同
产品 API，不得建立 `/api/v1/mobile` 副本。

### `me`、`elfies` 与 `admin`

`/me` 只表达当前成员的身份、资料、偏好、密码、领养流程、对话关系和联系人关系。
主体必须从认证会话推导，禁止客户端提交另一个 `user_id` 冒充他人。

精灵是独立资源，统一使用复数 `/elfies`，禁止新增 `/elfie` 或 `/me/elfies`：

- `GET /api/v1/elfies` 返回当前主体可见的精灵集合，不默认等于“我的精灵”；
- “我的精灵”使用明确、受类型约束的关系过滤，例如 `relationship=owned`；
- 成员投影返回稳定的 `relationship` 和 `permissions`，由服务端决定字段和动作权限；
- `/api/v1/admin/elfies` 是同一事实源的管理员投影，使用独立响应模型，不复制精灵
  事实，也不让成员接口根据角色静默改变结构。

`/admin` 是家庭管理员的全局管理范围，不代表企业级审批或复杂 RBAC。主要资源归属为：

- `/admin/users`：成员生命周期和管理员投影；
- `/admin/elfies`：全部精灵的管理员投影；
- `/admin/nest`：唯一精灵巢、床位和布局语义；
- `/admin/model-providers`：远程模型连接、本地 Ollama 和模型资源；
- `/admin/food-packages`：粮食包与模型角色绑定；
- `/admin/settings`：其他全局配置；
- `/admin/runtime`：运行状态和管理投影。

### 模型 Provider、Setup 与系统设置

Ollama 是模型 Provider，不建立顶层 `/local-models` 业务域。Setup 只读取安装所需的
受限投影，完整管理归属 `/admin/model-providers`。Setup Route 和 Admin Route 必须
复用同一 Feature/Service 与 Adapter；模型检测、扫描、推荐、下载和保存逻辑不得复制。
模型候选目录是推荐、安装校验和管理页面的唯一事实源。

工具与系统能力统一归属 `/admin/settings`，但配置归属一致不等于把底层执行实现合并：

- 精灵默认额度等全局规则属于 `settings/elfies`；
- 唯一精灵巢的床位数只属于 `/admin/nest`，设置中不得建立第二个可写容量事实；
- 网络搜索、本地文件和未来外部能力属于 `settings/capabilities`，每项能力可以有独立
  开关、配置、状态和验证动作；
- 低频运行参数属于 `settings/runtime`；
- 只有确实需要家庭管理员配置的安全参数才属于 `settings/security`。

系统设置的每个模块必须使用独立模型，禁止恢复 `{section}` 加任意字典的通用接口。

### 精灵的外部身体

现实世界载体在产品语义上属于精灵的外部身体，归属 `/elfies/{elfie_id}/bodies`，
不建立与精灵并列的顶层设备事实。配对与凭据属于该领域的安全边界：服务端必须从
受信凭据解析绑定关系，不能信任客户端自行声明的 `elfie_id`。具体协议在实现该能力
时由独立、受测试保护的协议契约定义。

## HTTP 与数据契约

### URL、字段和方法

- URL 使用小写、复数资源名和 kebab-case，末尾不加 `/`；
- JSON 字段和查询参数使用 snake_case；
- 路径参数使用 `user_id`、`elfie_id` 等明确名称，禁止通用 `id`；
- 同一实体始终使用同一种稳定 ID，不以名称、顺序或显示标签寻址；
- 时间使用带时区的 ISO 8601 UTC 字符串；布尔字段使用肯定语义；枚举由模型约束；
- `GET` 只读，`POST` 创建资源或执行明确动作，`PATCH` 局部修改，`PUT` 完整替换，
  `DELETE` 删除资源或解除关系；
- 创建返回 `201`，普通成功返回 `200`，无响应体返回 `204`，异步任务返回 `202` 和
  可查询任务标识；
- 类型错误返回 `422`，未认证 `401`，权限不足 `403`，不存在 `404`，状态冲突 `409`；
- 禁止用 `200` 加 `{success: false}` 表达失败。

### 请求与响应模型

- 每个请求体和响应都使用命名、严格的 Pydantic Model，Route 必须声明
  `response_model`；
- 禁止新增 `Dict[str, Any]`、任意 section payload、无约束字典或按角色动态增删字段；
- 同一资源的成员、管理员和 Setup 投影使用不同的明确模型；
- 集合响应使用命名 envelope，至少包含 `items`；需要分页时统一使用明确游标字段；
- 可空字段必须区分缺失、未知和 `null`；
- 密码、密钥、Token 和完整凭据不得进入普通响应、日志或错误详情；
- 后端 Pydantic/OpenAPI 是 HTTP 契约的权威来源。建立类型生成前，前端必须在 API
  Client 边界使用严格 Schema 校验原始响应；
- 聚合响应必须是稳定、只读、可追溯到权威 Feature 的业务投影，不能只为页面排版
  临时拼装第二份事实。

### 错误模型

所有错误使用统一 envelope、稳定机器错误码和匹配的 HTTP 状态：

```json
{
  "error": {
    "code": "elfie_capacity_reached",
    "message": "精灵巢床位已满",
    "details": {"capacity": 4}
  }
}
```

调用方只能根据 `error.code` 分支，不得解析中英文 `message`。`details` 只能包含安全、
结构化且与当前错误直接相关的数据；同一业务错误在不同 Route 中使用同一错误码和
HTTP 状态。

## 认证、授权与分层

- 浏览器 REST 和聊天 WebSocket 使用同源会话；状态修改继续执行 CSRF 校验；
- Setup 使用受限、可过期的 Setup 会话，只访问明确允许的安装资源；
- `/elfies` 的字段和动作由服务端关系与权限投影决定，不能仅靠前端隐藏按钮；
- 每个 `/admin` Route 显式执行管理员认证；路径名称本身不是权限控制；
- `/admin/settings` 不提供物种启用或审批字段；`/me/adoption` 的物种选项必须来自
  `elfie/profile` 注册表，新增已验证物种无需管理员写入设置即可对已有安装可用；
- 外部身体使用独立最小权限凭据，不复用管理员或 Runtime authority 凭据；
- Observer 和 Runtime 继续遵守根目录的 authority 边界。

标准调用方向是：

```text
Route / WebSocket boundary
        -> app/features 用例或 app/orchestration 编排
        -> Repository / Adapter
```

Route 只负责认证、CSRF、参数解析、调用用例、错误映射和响应序列化。API 层不得直接
SQL、确定数据根、读写 YAML/SQLite 第二事实源，也不得持有业务规则、模型推荐算法、
Ollama 生命周期、Nest 几何或 Runtime authority。跨 Setup/Admin 或 Web/Mobile 共享
Feature/Service，不复制 Route 函数。业务异常由 Feature 使用明确异常类型表达，再由
Route 统一映射。Route 需要的用例服务、查询服务和实时门面必须由组合根注入；不得在
Route、依赖函数或 API app 工厂内临时创建 Repository、Registry 或其他具体 Adapter。

API 代码按 `auth`、`setup`、`me`、`elfies`、`admin`、`observer`、`realtime` 等
业务域组织，不按页面组织。文件可以在领域变大后拆分，但 Router 前缀、模型和 Feature
归属必须保持单一权威入口。

## WebSocket 基本契约

- 路径使用 `/api/v1/ws/...`；
- 协议必须声明版本、事件类型、事件 ID、时间戳和强类型 payload；
- WebSocket 只负责实时传输，不成为聊天历史或设备关系的事实源；
- 鉴权、重连、确认、错误和幂等语义由对应协议测试保护；
- 禁止发送只有单个页面理解的临时 JSON。

## 验证与防回退

- API 变更必须盘点 Route、生产与测试调用方、Feature/Repository、目标路径和删除条件，
  并验证全部真实调用方；“路由已注册”或“前端没调用”都不能单独证明接口有价值或无用。
- 永久架构门禁必须拒绝未版本化产品 Route、已删除路径、API 层直接 SQL、松散请求/
  响应、重复 method + path 和前端页面硬编码 API；不得用长期 allowlist 掩盖违规。
