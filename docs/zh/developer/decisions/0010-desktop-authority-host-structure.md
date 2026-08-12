# ADR-0010：Desktop authority host 结构遵循所有权

- **状态：** 已接受
- **日期：** 2026-08-12
- **范围：** Desktop Interface 源码结构与 Bootstrap authority host

## 背景

系统契约已经把 `app/interfaces/desktop/` 限定为可见 Observer 和 lifecycle client，
并由 `app/bootstrap/` 拥有生产组合。但永久项目结构测试仍要求
`app/interfaces/desktop/src/role_dispatch.ts` 存在；该旧模块承担 authority host
分派，会迫使已经退役的宿主实现继续留在 Interface，与现行所有权边界冲突。

## 决策

Desktop Interface 源码结构只要求 Observer/lifecycle 模块，不再要求
`role_dispatch.ts`。Electron authority host 及其打包配置归属
`app/bootstrap/desktop_host/`。本治理步骤先删除矛盾的结构要求，再由独立产品迁移
删除旧模块；删除完成后，再由后续治理收口增加永久防回退断言。本次不改变模块
所有权、authority 或依赖方向。

## 后果

产品迁移必须在本治理变更落地后才能删除旧 Interface host。架构套件继续保护必要的
lifecycle client，但不再强迫退役宿主留在 Interface。
