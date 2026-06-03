# 测试问题修复计划

## TL;DR

> **目标**: 修复测试中的两个问题，确保所有测试通过
> 
> **交付物**:
> - 修复 test/test_anatomy.py 的浮点数比较问题
> - 修复 test/test_engine.py 的 mock amygdala 问题
> 
> **预计工作量**: Quick (简单修复)
> **并行执行**: NO (顺序修复)
> **关键路径**: 修复test_anatomy.py → 修复test_engine.py → 验证

---

## Context

### 问题背景
运行 `pytest test/ -v` 发现3个测试失败/错误：
1. **FAILED** test/test_anatomy.py::TestBipedAnatomy::test_joint_limits
   - 原因：浮点数精度问题
2. **ERROR** test/test_engine.py::TestElfieNestEngine::test_coordinator_register_elfie
   - 原因：mock对象缺少amygdala属性
3. **ERROR** test/test_engine.py::TestElfieNestEngine::test_room_tick_updates_elfies
   - 原因：同上

### 分析结果
已完成问题分析（bg_b7f6a9b9），确定了修复方案。

---

## Work Objectives

### 核心目标
修复测试问题，确保所有289个测试通过。

### 具体任务

#### Task 1: 修复test_anatomy.py
- 位置：test/test_anatomy.py 第219-220行
- 问题：使用assertEqual比较浮点数math.pi/2
- 修复：改为assertAlmostEqual，精度places=2

#### Task 2: 修复test_engine.py
- 位置：test/test_engine.py 第27行
- 问题：MagicMock(spec=ElfieIndividual)没有amygdala属性
- 修复：显式创建amygdala mock对象

#### Task 3: 验证所有测试通过
- 运行pytest test/ -v
- 确保所有测试通过

---

## TODOs

- [ ] 1. 修复test_anatomy.py的浮点数比较问题

  **What to do**:
  - 编辑 test/test_anatomy.py
  - 第219-220行，将 `assertEqual` 改为 `assertAlmostEqual(..., places=2)`
  
  **修复前**:
  ```python
  self.assertEqual(anatomy.joints["head_yaw"].min_angle, -math.pi/2)
  self.assertEqual(anatomy.joints["head_yaw"].max_angle, math.pi/2)
  ```
  
  **修复后**:
  ```python
  self.assertAlmostEqual(anatomy.joints["head_yaw"].min_angle, -math.pi/2, places=2)
  self.assertAlmostEqual(anatomy.joints["head_yaw"].max_angle, math.pi/2, places=2)
  ```

  **Must NOT do**:
  - 不要修改其他行

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Commit**: NO (等待所有修复完成一起提交)

- [ ] 2. 修复test_engine.py的mock问题

  **What to do**:
  - 编辑 test/test_engine.py
  - 第27行，在 `elfie.amygdala.get_dominant_mood.return_value = "happy"` 前添加一行
  
  **修复前**:
  ```python
  elfie.amygdala.get_dominant_mood.return_value = "happy"
  ```
  
  **修复后**:
  ```python
  elfie.amygdala = MagicMock()
  elfie.amygdala.get_dominant_mood.return_value = "happy"
  ```

  **Must NOT do**:
  - 不要修改其他行

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Commit**: NO (等待所有修复完成一起提交)

- [ ] 3. 验证所有测试通过

  **What to do**:
  - 运行 `pytest test/ -v`
  - 确认所有测试通过
  - 检查测试数量（预期约289个）

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Commit**: YES - message: `fix: 修复测试问题`

---

## Verification Strategy

### 验证命令
```bash
pytest test/ -v --tb=short
```

### 预期结果
- 所有测试通过
- 无ERROR
- 无FAILED
- 测试数量约289个

---

## Success Criteria

- [ ] test_anatomy.py的test_joint_limits测试通过
- [ ] test_engine.py的两个测试通过
- [ ] 所有289个测试通过
- [ ] 已提交修复

---

## Commit Strategy

- **1**: `fix: 修复测试问题` - test/test_anatomy.py, test/test_engine.py
