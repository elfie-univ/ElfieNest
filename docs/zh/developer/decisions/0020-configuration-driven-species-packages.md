# ADR-0020：配置驱动的物种包

- **状态：** 已接受
- **日期：** 2026-08-15
- **范围：** 物种注册、展示资源、Genesis 输入和 Godot 外观绑定

## 背景

物种元数据、外观默认值和 Genesis 输入曾经分散在 Profile 常量、前端图片文件和
Godot 映射中。新增物种需要修改多个互不相关的事实源，也容易漏掉展示资源。候选
名字也不应该属于物种定义，因为它是在领养过程中生成的。

## 决策

使用固定的内置注册文件 `config/species/catalog.yaml`，并为每个物种建立一个
`config/species/<package>/` 目录。物种包拥有 canon 链接、显示信息、可调外观控制项及
范围、Genesis 输入，以及不同的 `headshot.png` 和 `full-body.png` 展示资源。由
Infrastructure 加载并校验目录，再把不可变的类型化值注入 Profile、Genesis 和
Adoption。

状态规则固定如下：`published` 只有在配置包和 Godot 包完整且都通过校验后才能被领养；
`retired` 仍可解析已有档案但不能被领养；`draft` 从运行时选项中排除。前端从 API 获取
可用物种和图片 URL，不拥有物种列表或图片事实源。Godot 仍是 3D 身体和渲染的唯一
权威；schema v2 Manifest 负责语义控制项到骨骼的绑定。

## 结果

- 新增物种主要是增加通过校验的配置包和匹配的 Godot 包，不再修改 Profile 或前端白名单。
- 缺失字段、缺失/非法 PNG、重复展示图片和不完整 Genesis 数据会在发布前失败关闭。
- 已有档案可以继续解析 retired 物种，不会因此重新开放领养。
- 将来修改外观协议时，必须同时升级 Manifest/配置协议版本，并补充 Godot/Python 聚焦校验。
