# 公开设计文档归位与阅读规则

本文件作用于 `docs/zh/developer/designs/` 及其所有子路径。英文镜像目录遵守相同规则。

## 所有权与物理目录

- `designs/index.md` 只是目录页，不是父级设计，也不产生另一套权威层级。
- 全局系统设计是独立的上级设计。本次整理不移动它，本文件也不为它指定公开路径。
  `designs/elfie/elfie-top-level-module-design.md` 只是 Elfie 模块的顶级设计；
  不得把它当成全局系统设计的替代品。
- 逻辑上的一级所有者是 `app`、`infrastructure`、`elfie` 和 `nest`。
- `elfie` 内部的逻辑子模块是 `brain`、`embodiment`、`communication` 和 `genesis`。
- 只有某个所有者拥有多篇设计时才建立物理目录；只有某个子模块拥有多篇文档时才继续
  建立子目录。不要为了未来模块创建空目录或 `index.md`。
- 只有一篇文档时，可以继续放在当前父目录，并在关系块中声明所有者和上级设计。当前
  已成组的文档位于 `elfie/brain/` 和 `elfie/embodiment/`，当前 App 文档位于 `app/`。

## 上级引用与阅读顺序

整理时保留现有设计正文，只新增或修正路径和少量关系块。每篇设计文档声明：

```text
所属模块：
上级设计：
下级设计：
规范性契约：
当前架构：
一致性台账：
领域资料来源：
```

修改局部内容时，从全局设计读到所属模块设计，再读子模块设计、目标文档、相关契约和
一致性台账。子设计只能细化上级设计，不能悄悄重新定义上级的所有权或 authority。
规范性系统规则是 `../contracts/system.md`，已验证的当前实现地图是 `../architecture/index.md`；
它们与目标设计属于不同层，不能互相替代。

## Elfie Brain

`Selfhood` 是 Brain 的第 3 个系统，应放在 `elfie/brain/` 下。其他 Brain 系统遵循已采纳
的十系统设计。Skill 和 Tool 是 Reasoning Core 使用的阶段性能力，不是额外的 Brain
系统，也不是 `brain`、`embodiment`、`communication`、`genesis` 的平级模块；除非以后
形成独立且已采纳的设计，否则不要创建 `skills/` 分支。

前端、Godot 和其他代码/资源目录旁的实现规范与制作指南继续靠近实际所有者，不复制到
中央设计目录。
