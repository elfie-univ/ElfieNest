# ElfieNest 情绪系统实现计划

## TL;DR

> **Quick Summary**: 重构情绪系统，从4种情绪扩展到8种，引入强度识别、饱和增长、分阶段衰减、频率维护、融合去重等高级特性，并集成本地小模型实现毫秒级情绪识别。
>
> **Deliverables**:
> - 扩展的情绪类型（8种）
> - 强度识别机制
> - 饱和增长 + 分阶段衰减公式
> - 频率信息维护（deque滑动窗口）
> - 融合去重机制
> - 本地小模型集成（可选）
> - 单元测试 + 集成测试
>
> **Estimated Effort**: Large
> **Parallel Execution**: YES - 4 waves
> **Critical Path**: Phase 1 → Phase 2 → Phase 3 → Phase 4

---

## Context

### Original Request
用户要求实现完整的情绪系统，包括：
1. 8种情绪类型（扩展自当前的4种）
2. 强度识别机制
3. 饱和增长公式
4. 分阶段衰减公式
5. 频率信息维护
6. 融合去重机制
7. 本地小模型集成

### Interview Summary
**Key Discussions**:
- 情绪类型：确定为8种（happiness, sadness, anger, fear, surprise, disgust, boredom, attachment）
- 强度识别：每个输入携带intensity (0.0-1.0)，不同强度的刺激产生不同的情绪增量
- 本地小模型：文本→RoBERTa(400MB), 图像→DeepFace(100MB), 语音→pyworld(50MB)
- 增长公式：饱和增长，值越高增长越慢
- 衰减公式：分阶段衰减，高值快消散，低值慢残留
- 频率慢化：连续刺激延缓衰减

**Research Findings**:
- 当前实现：4种情绪，简单线性更新，简单指数衰减
- 现成小模型：不需要GPU，总大小约550MB，毫秒级响应
- **CRITICAL BUG**: 代码中import的 `elfie.core_systems` 目录不存在

### Metis Review
**Identified Gaps** (addressed):
1. **Broken imports**: `elfie.core_systems` → 需要修复为 `elfie.brain`
2. **Data migration**: anxiety/jealousy 如何迁移到新情绪类型？
3. **Backward compatibility**: 现有代码调用 `update_emotion(name, delta)` 需要兼容
4. **Test breakage**: 测试代码访问 `emotions["anxiety"]` 会失败
5. **Dominant mood algorithm**: 需要新的算法处理8种情绪
6. **Intensity source**: 强度值从哪里来？

---

## Work Objectives

### Core Objective
重构ElfieNest的情绪系统，实现毫秒级响应、强度敏感、符合人类情绪体验的高级情绪模型。

### Concrete Deliverables
- `elfie/brain/emotion/emotion_types.py` - 情绪类型定义和配置
- `elfie/brain/emotion/emotion_input.py` - EmotionInput数据结构
- `elfie/brain/emotion/emotion_state.py` - 重构后的情绪状态管理
- `elfie/brain/emotion/decay_calculator.py` - 分阶段衰减
- `elfie/brain/emotion/emotion_system.py` - 情绪系统核心
- `elfie/brain/emotion/detector/` - 情绪检测器（可选）
- 单元测试和集成测试

### Definition of Done
- [ ] 所有单元测试通过（包括mock ML模型的测试）
- [ ] 现有代码兼容性保持（不破坏现有调用）
- [ ] `python main.py` 运行10个ticks无错误
- [ ] 性能测试：1000次情绪更新 < 100ms

### Must Have
- 8种情绪类型完整实现
- 强度识别机制（intensity参数）
- 饱和增长公式
- 分阶段衰减公式
- 频率信息维护
- 融合去重机制
- 向后兼容性

### Must NOT Have (Guardrails)
- ❌ 不创建"情绪插件系统"或动态注册表（YAGNI）
- ❌ 不添加神经网络训练代码（只用预训练模型）
- ❌ 不过度工程化配置（先用硬编码默认值）
- ❌ 不修改 `.elfie_memories.json` 格式
- ❌ 不添加实时可视化代码
- ❌ 不创建抽象的"EmotionEngine"基类层次

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** - ALL verification is agent-executed.

### Test Decision
- **Infrastructure exists**: YES (pytest)
- **Automated tests**: TDD (Red-Green-Refactor)
- **Framework**: pytest
- **Each task follows RED (failing test) → GREEN (minimal impl) → REFACTOR**

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Backend**: Use Bash (python -c) - Import, call functions, assert outputs
- **Performance**: Use Bash (time python -c) - Measure execution time

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation - 修复和基础重构):
├── Task 1: 修复broken imports [quick]
├── Task 2: 定义情绪类型和配置 [quick]
├── Task 3: 创建EmotionInput数据结构 [quick]
└── Task 4: 设计迁移策略 [quick]

Wave 2 (Core Implementation - 核心实现):
├── Task 5: 实现饱和增长公式 [quick]
├── Task 6: 实现分阶段衰减公式 [quick]
├── Task 7: 实现频率信息维护 [quick]
├── Task 8: 实现融合去重机制 [quick]
└── Task 9: 重构情绪状态管理 [deep]

Wave 3 (Integration - 集成):
├── Task 10: 更新decay_calculator.py [quick]
├── Task 11: 更新现有调用方 [unspecified-high]
├── Task 12: 实现主导情绪算法 [quick]
└── Task 13: 编写单元测试 [unspecified-high]

Wave 4 (Optional - ML Models):
├── Task 14: 实现文本情绪检测器 [unspecified-high]
├── Task 15: 实现图像情绪检测器 [unspecified-high]
├── Task 16: 实现语音情绪检测器 [unspecified-high]
└── Task 17: 统一检测接口 [quick]

Critical Path: Task 1 → Task 4 → Task 5-9 → Task 10-13 → Task 14-17
Parallel Speedup: ~60% faster than sequential
Max Concurrent: 5 (Wave 2)
```

### Dependency Matrix

- **1-4**: Independent
- **5-9**: Depend on Task 2, 3
- **10-13**: Depend on Task 5-9
- **14-17**: Independent from core, can run in parallel with Wave 3

---

## TODOs

- [x] 1. 修复broken imports

  **What to do**:
  - 搜索所有引用 `elfie.core_systems` 的文件
  - 修改为正确的导入路径 `elfie.brain`
  - 确保所有import语句正确
  - 运行测试验证修复

  **Must NOT do**:
  - 不要修改功能代码，只修复import路径
  - 不要删除任何文件

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 简单的查找替换任务
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `elfie/brain/emotion/emotional_state.py:4` - 错误的import `elfie.core_systems.emotion`
  - `elfie/elfie_individual.py:6` - 错误的import

  **Acceptance Criteria**:
  - [ ] 所有 `elfie.core_systems` 替换为 `elfie.brain`
  - [ ] `python -c "from elfie.brain.emotion import AmygdalaEmotionalState"` 成功
  - [ ] 无import错误

  **QA Scenarios**:
  ```
  Scenario: Import verification
    Tool: Bash (python -c)
    Steps:
      1. python -c "from elfie.brain.emotion import AmygdalaEmotionalState"
      2. python -c "from elfie.brain.emotion import EmotionDecayCalculator"
    Expected Result: No ImportError
    Evidence: .sisyphus/evidence/task-1-import-check.log
  ```

  **Commit**: YES
  - Message: `fix(emotion): repair broken imports from core_systems to brain`
  - Files: All files with import errors

- [x] 2. 定义情绪类型和配置

  **What to do**:
  - 创建 `elfie/brain/emotion/emotion_types.py`
  - 定义8种情绪类型枚举
  - 定义每种情绪的配置（base_delta, baseline, half_life, max_value）
  - 创建配置加载函数

  **Must NOT do**:
  - 不要创建动态注册表
  - 不要过度抽象

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 数据结构定义，无复杂逻辑
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 5-9
  - **Blocked By**: None

  **References**:
  - `elfie/brain/emotion/emotional_state.py:11-16` - 当前的4种情绪定义
  - `.sisyphus/drafts/情绪系统完整设计方案.md` - 设计文档中的情绪类型定义

  **Acceptance Criteria**:
  - [ ] 文件创建：`elfie/brain/emotion/emotion_types.py`
  - [ ] 8种情绪枚举定义
  - [ ] 每种情绪有base_delta, baseline, half_life, max_value
  - [ ] 单元测试通过

  **QA Scenarios**:
  ```
  Scenario: Emotion types verification
    Tool: Bash (python -c)
    Steps:
      1. python -c "from elfie.brain.emotion.emotion_types import EmotionType, EMOTION_CONFIGS"
      2. assert len(EMOTION_CONFIGS) == 8
      3. assert 'happiness' in EMOTION_CONFIGS
      4. assert EMOTION_CONFIGS['fear']['base_delta'] == 40
    Expected Result: All assertions pass
    Evidence: .sisyphus/evidence/task-2-emotion-types.log
  ```

  **Commit**: NO (groups with Task 3, 4)

- [x] 3. 创建EmotionInput数据结构

  **What to do**:
  - 创建 `elfie/brain/emotion/emotion_input.py`
  - 使用 @dataclass 定义 EmotionInput
  - 包含字段：emotion, intensity, source, event_id, timestamp, metadata
  - 添加验证方法

  **Must NOT do**:
  - 不要添加复杂的验证逻辑
  - 不要创建继承层次

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 简单的数据类定义
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 5-9
  - **Blocked By**: None

  **References**:
  - `.sisyphus/drafts/情绪系统完整设计方案.md` - EmotionInput定义

  **Acceptance Criteria**:
  - [ ] 文件创建：`elfie/brain/emotion/emotion_input.py`
  - [ ] EmotionInput dataclass定义
  - [ ] intensity 范围验证 (0.0-1.0)
  - [ ] 单元测试通过

  **QA Scenarios**:
  ```
  Scenario: EmotionInput creation
    Tool: Bash (python -c)
    Steps:
      1. from elfie.brain.emotion.emotion_input import EmotionInput
      2. inp = EmotionInput(emotion='fear', intensity=0.8, source='text', event_id='e1')
      3. assert inp.intensity == 0.8
      4. assert inp.validate() == True
    Expected Result: EmotionInput创建成功
    Evidence: .sisyphus/evidence/task-3-emotion-input.log
  ```

  **Commit**: NO (groups with Task 2, 4)

- [x] 4. 设计迁移策略

  **What to do**:
  - 分析当前emotion状态数据（如果有persisted state）
  - 设计anxiety → fear的映射策略
  - 设计jealousy → ?的映射策略（或保留为新情绪）
  - 创建迁移函数
  - 添加向后兼容的别名

  **Must NOT do**:
  - 不要修改 `.elfie_memories.json` 格式
  - 不要丢失用户数据

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 主要是设计决策和简单映射
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 9
  - **Blocked By**: None

  **References**:
  - `elfie/brain/emotion/emotional_state.py:11-16` - 当前的4种情绪
  - `.sisyphus/drafts/情绪系统完整设计方案.md` - 新的8种情绪

  **Acceptance Criteria**:
  - [ ] 迁移策略文档化（在代码注释中）
  - [ ] anxiety → fear 映射定义
  - [ ] jealousy 处理方案（保留或映射）
  - [ ] 向后兼容的别名支持

  **QA Scenarios**:
  ```
  Scenario: Migration compatibility
    Tool: Bash (python -c)
    Steps:
      1. from elfie.brain.emotion import EmotionSystem
      2. system = EmotionSystem()
      3. system.update('anxiety', delta=10.0)  # Old API
      4. assert 'fear' in system.emotions  # Mapped to fear
    Expected Result: 旧API仍然工作
    Evidence: .sisyphus/evidence/task-4-migration.log
  ```

  **Commit**: YES
  - Message: `feat(emotion): define emotion types and migration strategy`
  - Files: emotion_types.py, emotion_input.py, migration相关代码

- [x] 5. 实现饱和增长公式

  **What to do**:
  - 在 `emotion_state.py` 中实现饱和增长公式
  - 公式：`delta = base_delta × intensity × accumulate_rate × (1 - value/max_value)`
  - 默认 accumulate_rate = 0.5
  - 添加单元测试验证公式正确性

  **Must NOT do**:
  - 不要过度复杂化
  - 不要添加可配置的公式（先用固定公式）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 数学公式实现，逻辑清晰
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 9
  - **Blocked By**: Task 2

  **References**:
  - `.sisyphus/drafts/情绪系统完整设计方案.md` - 饱和增长公式说明
  - `elfie/brain/emotion/emotional_state.py:18-29` - 当前的update_emotion方法

  **Acceptance Criteria**:
  - [ ] 方法签名：`accumulate(emotion: str, delta: float, intensity: float = 0.5)`
  - [ ] 饱和因子正确计算
  - [ ] 单元测试：高值时增量小，低值时增量大

  **QA Scenarios**:
  ```
  Scenario: Saturation growth verification
    Tool: Bash (python -c)
    Steps:
      1. state = EmotionState('happiness', value=90.0)
      2. state.accumulate(delta=20.0, intensity=1.0)
      3. expected = 90 + 20 * 1.0 * 0.5 * (1 - 90/100) = 91.0
      4. assert abs(state.value - 91.0) < 0.1
    Expected Result: 饱和增长正确
    Evidence: .sisyphus/evidence/task-5-saturation.log
  ```

  **Commit**: NO (groups with Task 6-9)

- [x] 6. 实现分阶段衰减公式

  **What to do**:
  - 重构 `decay_calculator.py`
  - 实现分阶段衰减：高值区半衰期×0.3，低值区半衰期×3
  - 阈值默认：50
  - 每种情绪独立的baseline
  - 添加单元测试

  **Must NOT do**:
  - 不要修改现有的衰减逻辑（先复制再修改）
  - 不要创建复杂的配置系统

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 数学公式实现
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 10
  - **Blocked By**: Task 2

  **References**:
  - `elfie/brain/emotion/decay_calculator.py` - 当前的衰减实现
  - `.sisyphus/drafts/情绪系统完整设计方案.md` - 分阶段衰减说明

  **Acceptance Criteria**:
  - [ ] 高值区（value > threshold）使用快速衰减
  - [ ] 低值区（value ≤ threshold）使用慢速衰减
  - [ ] 每种情绪衰减到各自的baseline
  - [ ] 单元测试验证

  **QA Scenarios**:
  ```
  Scenario: Phased decay verification
    Tool: Bash (python -c)
    Steps:
      1. state_high = EmotionState('anger', value=80.0)
      2. state_low = EmotionState('anger', value=20.0)
      3. decay(state_high, dt=60)
      4. decay(state_low, dt=60)
      5. # High zone decays faster
      6. assert state_high.value < 70
      7. assert state_low.value > 18  # Low zone decays slower
    Expected Result: 分阶段衰减正确
    Evidence: .sisyphus/evidence/task-6-decay.log
  ```

  **Commit**: NO (groups with Task 5, 7-9)

- [x] 7. 实现频率信息维护

  **What to do**:
  - 在 `EmotionState` 中添加 `expire_times: deque`
  - 实现 `record_input(current_time)` 方法
  - 实现 `clean_expired(current_time)` 方法
  - 实现 `get_recent_count(current_time)` 方法
  - 实现 `get_slow_factor(current_time)` 方法

  **Must NOT do**:
  - 不要使用固定大小的deque（用时间窗口）
  - 不要在每次tick都重建deque

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: deque操作，逻辑简单
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 9
  - **Blocked By**: Task 2

  **References**:
  - `.sisyphus/drafts/情绪系统完整设计方案.md` - 频率维护算法

  **Acceptance Criteria**:
  - [ ] deque存储过期时间
  - [ ] 自动清理过期记录
  - [ ] slow_factor = 1 + recent_count × 0.5
  - [ ] 单元测试

  **QA Scenarios**:
  ```
  Scenario: Frequency tracking
    Tool: Bash (python -c)
    Steps:
      1. state = EmotionState('fear')
      2. for i in range(5): state.record_input(time.time())
      3. slow_factor = state.get_slow_factor(time.time())
      4. assert slow_factor == 1 + 5 * 0.5 == 3.5
    Expected Result: 频率慢化因子正确
    Evidence: .sisyphus/evidence/task-7-frequency.log
  ```

  **Commit**: NO (groups with Task 5-6, 8-9)

- [x] 8. 实现融合去重机制

  **What to do**:
  - 创建 `elfie/brain/emotion/fusion/deduplicator.py`
  - 使用set存储已处理的event_id
  - 实现TTL过期清理（默认60秒）
  - 实现强度融合（加权平均）

  **Must NOT do**:
  - 不要存储所有历史（只保留最近60秒）
  - 不要过度优化

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 简单的set操作和平均计算
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 9
  - **Blocked By**: Task 3

  **References**:
  - `.sisyphus/drafts/情绪系统完整设计方案.md` - 融合去重机制

  **Acceptance Criteria**:
  - [ ] event_id去重实现
  - [ ] TTL过期清理实现
  - [ ] 加权平均强度融合
  - [ ] 单元测试

  **QA Scenarios**:
  ```
  Scenario: Deduplication
    Tool: Bash (python -c)
    Steps:
      1. dedup = EventDeduplicator(ttl=60)
      2. assert dedup.is_new('e1') == True
      3. dedup.mark_processed('e1')
      4. assert dedup.is_new('e1') == False
    Expected Result: 去重工作正常
    Evidence: .sisyphus/evidence/task-8-dedup.log
  ```

  **Commit**: NO (groups with Task 5-7, 9)

- [x] 9. 重构情绪状态管理

  **What to do**:
  - 重构 `emotional_state.py` 为新的 `EmotionSystem`
  - 整合饱和增长、分阶段衰减、频率维护、融合去重
  - 保持向后兼容：`update_emotion(name, delta)` 仍然工作
  - 添加新方法：`process_input(EmotionInput)`

  **Must NOT do**:
  - 不要破坏现有测试
  - 不要删除旧方法（添加deprecation warning）

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 需要整合多个组件，逻辑复杂
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential
  - **Blocks**: Task 10-13
  - **Blocked By**: Task 2, 3, 4, 5, 6, 7, 8

  **References**:
  - `elfie/brain/emotion/emotional_state.py` - 当前实现
  - Task 5-8的实现

  **Acceptance Criteria**:
  - [ ] 新类 `EmotionSystem` 创建
  - [ ] 8种情绪初始化
  - [ ] `update_emotion()` 向后兼容
  - [ ] `process_input()` 新方法
  - [ ] `get_dominant_mood()` 更新为8种情绪
  - [ ] 单元测试

  **QA Scenarios**:
  ```
  Scenario: Backward compatibility
    Tool: Bash (python -c)
    Steps:
      1. from elfie.brain.emotion import EmotionSystem
      2. system = EmotionSystem()
      3. system.update_emotion('fear', 20.0)  # Old API
      4. assert system.emotions['fear'] > 0
    Expected Result: 旧API仍然工作
    Evidence: .sisyphus/evidence/task-9-compat.log
  
  Scenario: New input processing
    Tool: Bash (python -c)
    Steps:
      1. from elfie.brain.emotion import EmotionSystem, EmotionInput
      2. system = EmotionSystem()
      3. inp = EmotionInput(emotion='fear', intensity=0.8, source='text', event_id='e1')
      4. system.process_input(inp)
      5. assert system.emotions['fear'] > 0
    Expected Result: 新API工作正常
    Evidence: .sisyphus/evidence/task-9-new-api.log
  ```

  **Commit**: YES
  - Message: `feat(emotion): implement core emotion system with saturation, phased decay, frequency, and dedup`
  - Files: emotion_state.py, accumulator/, fusion/
  - Pre-commit: `python -m pytest test/`

- [x] 10. 更新decay_calculator.py

  **What to do**:
  - 更新 `decay_calculator.py` 使用新的分阶段衰减
  - 支持8种情绪
  - 每种情绪独立的baseline和half_life

  **Must NOT do**:
  - 不要删除旧代码（保留向后兼容）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 简单的更新和配置
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 11
  - **Blocked By**: Task 6, 9

  **References**:
  - `elfie/brain/emotion/decay_calculator.py` - 当前实现
  - Task 6的分阶段衰减实现

  **Acceptance Criteria**:
  - [ ] 支持8种情绪衰减
  - [ ] 分阶段衰减集成
  - [ ] 单元测试

  **QA Scenarios**:
  ```
  Scenario: Decay for 8 emotions
    Tool: Bash (python -c)
    Steps:
      1. from elfie.brain.emotion import EmotionSystem, EmotionDecayCalculator
      2. system = EmotionSystem()
      3. for emo in ['happiness', 'sadness', 'anger', 'fear', 'surprise', 'disgust', 'boredom', 'attachment']:
      4.     system.emotions[emo] = 80.0
      5. decay = EmotionDecayCalculator()
      6. decay.decay_emotions(system, dt=60)
      7. for emo in system.emotions:
      8.     assert system.emotions[emo] < 80.0
    Expected Result: 所有情绪都衰减
    Evidence: .sisyphus/evidence/task-10-decay-8.log
  ```

  **Commit**: NO (groups with Task 11-13)

- [x] 11. 更新现有调用方

  **What to do**:
  - 搜索所有使用 `amygdala.update_emotion()` 的地方
  - 更新为新的情绪名称（anxiety → fear等）
  - 更新 `emotions["anxiety"]` 直接访问
  - 确保所有调用方兼容

  **Must NOT do**:
  - 不要破坏功能
  - 不要修改测试文件（Task 13专门处理）

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 需要搜索和修改多个文件
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: None
  - **Blocked By**: Task 9

  **References**:
  - `elfie/body/reflex/reflex_arc.py` - 使用amygdala
  - `elfie/elfie_individual.py` - 使用amygdala

  **Acceptance Criteria**:
  - [ ] 所有调用方更新
  - [ ] `python main.py` 运行无错误
  - [ ] 向后兼容保持

  **QA Scenarios**:
  ```
  Scenario: Main runs without errors
    Tool: Bash (python)
    Steps:
      1. timeout 10 python main.py
    Expected Result: 运行10秒无错误退出
    Evidence: .sisyphus/evidence/task-11-main.log
  ```

  **Commit**: NO (groups with Task 10, 12-13)

- [x] 12. 实现主导情绪算法

  **What to do**:
  - 更新 `get_dominant_mood()` 方法
  - 设计8种情绪的优先级规则
  - 考虑情绪强度和唤醒度
  - 返回最显著的情绪

  **Must NOT do**:
  - 不要过度复杂化
  - 不要创建可配置的规则系统

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 简单的优先级逻辑
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: None
  - **Blocked By**: Task 9

  **References**:
  - `elfie/brain/emotion/emotional_state.py:31-42` - 当前的get_dominant_mood

  **Acceptance Criteria**:
  - [ ] 支持8种情绪
  - [ ] 返回正确的情绪名称
  - [ ] 单元测试

  **QA Scenarios**:
  ```
  Scenario: Dominant mood selection
    Tool: Bash (python -c)
    Steps:
      1. from elfie.brain.emotion import EmotionSystem
      2. system = EmotionSystem()
      3. system.emotions['fear'] = 80.0
      4. system.emotions['happiness'] = 60.0
      5. mood = system.get_dominant_mood()
      6. assert mood == 'fear'  # Highest value
    Expected Result: 返回最高值的情绪
    Evidence: .sisyphus/evidence/task-12-dominant.log
  ```

  **Commit**: NO (groups with Task 10-11, 13)

- [x] 13. 编写单元测试

  **What to do**:
  - 创建 `test/test_emotion_system.py`
  - 测试所有核心功能
  - 测试向后兼容性
  - 测试边界情况
  - Mock ML模型（不依赖真实模型）

  **Must NOT do**:
  - 不要依赖真实ML模型
  - 不要创建需要用户干预的测试

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 需要编写多个测试用例
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: None
  - **Blocked By**: Task 9

  **References**:
  - `test/test_embodied_perception.py` - 现有测试

  **Acceptance Criteria**:
  - [ ] 文件创建：`test/test_emotion_system.py`
  - [ ] 所有核心功能有测试
  - [ ] `python -m pytest test/test_emotion_system.py -v` 通过
  - [ ] 覆盖率 > 80%

  **QA Scenarios**:
  ```
  Scenario: All tests pass
    Tool: Bash (pytest)
    Steps:
      1. python -m pytest test/test_emotion_system.py -v
    Expected Result: All tests pass
    Evidence: .sisyphus/evidence/task-13-tests.log
  ```

  **Commit**: YES
  - Message: `feat(emotion): integrate new emotion system and update callers`
  - Files: decay_calculator.py, 所有调用方, test_emotion_system.py
  - Pre-commit: `python -m pytest test/`

- [x] 14. 实现文本情绪检测器（可选）

  **What to do**:
  - 创建 `elfie/brain/emotion/detector/text_detector.py`
  - 集成 Erlangshen-RoBERTa 模型
  - 实现懒加载（首次使用时加载）
  - 实现fallback到关键词检测

  **Must NOT do**:
  - 不要在模块加载时初始化模型
  - 不要依赖模型必须存在

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 需要集成第三方库
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4
  - **Blocks**: Task 17
  - **Blocked By**: None

  **References**:
  - `.sisyphus/drafts/情绪系统完整设计方案.md` - 文本检测实现

  **Acceptance Criteria**:
  - [ ] 文件创建：`detector/text_detector.py`
  - [ ] 模型懒加载
  - [ ] fallback机制
  - [ ] 单元测试（mock模型）

  **QA Scenarios**:
  ```
  Scenario: Text detection fallback
    Tool: Bash (python -c)
    Steps:
      1. from elfie.brain.emotion.detector import TextEmotionDetector
      2. detector = TextEmotionDetector()
      3. emotion, intensity = detector.detect("你真是太笨了！")
      4. assert emotion in ['anger', 'sadness']
    Expected Result: 即使无模型也能工作
    Evidence: .sisyphus/evidence/task-14-text.log
  ```

  **Commit**: NO (groups with Task 15-17)

- [x] 15. 实现图像情绪检测器（可选）

  **What to do**:
  - 创建 `elfie/brain/emotion/detector/image_detector.py`
  - 集成 DeepFace
  - 实现懒加载
  - 实现fallback

  **Must NOT do**:
  - 不要在模块加载时初始化
  - 不要依赖GPU

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 需要集成第三方库
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4
  - **Blocks**: Task 17
  - **Blocked By**: None

  **References**:
  - `.sisyphus/drafts/情绪系统完整设计方案.md` - 图像检测实现

  **Acceptance Criteria**:
  - [ ] 文件创建：`detector/image_detector.py`
  - [ ] DeepFace集成
  - [ ] fallback机制
  - [ ] 单元测试

  **QA Scenarios**:
  ```
  Scenario: Image detection fallback
    Tool: Bash (python -c)
    Steps:
      1. from elfie.brain.emotion.detector import ImageEmotionDetector
      2. detector = ImageEmotionDetector()
      3. emotion, intensity = detector.detect("fake_image.jpg")
      4. assert emotion in ['calm', 'happiness', 'sadness', 'anger', 'fear', 'surprise', 'disgust']
    Expected Result: 返回有效情绪
    Evidence: .sisyphus/evidence/task-15-image.log
  ```

  **Commit**: NO (groups with Task 14, 16-17)

- [x] 16. 实现语音情绪检测器（可选）

  **What to do**:
  - 创建 `elfie/brain/emotion/detector/audio_detector.py`
  - 集成 pyworld + librosa
  - 实现特征提取和规则判断
  - 实现fallback

  **Must NOT do**:
  - 不要依赖复杂的ML模型
  - 不要在模块加载时初始化

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 需要集成第三方库
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4
  - **Blocks**: Task 17
  - **Blocked By**: None

  **References**:
  - `.sisyphus/drafts/情绪系统完整设计方案.md` - 语音检测实现

  **Acceptance Criteria**:
  - [ ] 文件创建：`detector/audio_detector.py`
  - [ ] 特征提取实现
  - [ ] 规则判断实现
  - [ ] 单元测试

  **QA Scenarios**:
  ```
  Scenario: Audio detection
    Tool: Bash (python -c)
    Steps:
      1. from elfie.brain.emotion.detector import AudioEmotionDetector
      2. detector = AudioEmotionDetector()
      3. emotion, intensity = detector.detect("fake_audio.wav")
      4. assert emotion in ['calm', 'anger', 'sadness']
    Expected Result: 返回有效情绪
    Evidence: .sisyphus/evidence/task-16-audio.log
  ```

  **Commit**: NO (groups with Task 14-15, 17)

- [x] 17. 统一检测接口（可选）

  **What to do**:
  - 创建 `elfie/brain/emotion/detector/__init__.py`
  - 创建 `EmotionDetector` 统一接口
  - 根据输入类型自动选择检测器
  - 添加配置选项（启用/禁用ML模型）

  **Must NOT do**:
  - 不要强制加载所有模型
  - 不要创建复杂的配置系统

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 简单的接口整合
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential
  - **Blocks**: None
  - **Blocked By**: Task 14, 15, 16

  **References**:
  - `.sisyphus/drafts/情绪系统完整设计方案.md` - 统一检测接口

  **Acceptance Criteria**:
  - [ ] 文件创建：`detector/__init__.py`
  - [ ] `EmotionDetector` 类
  - [ ] 自动类型选择
  - [ ] 单元测试

  **QA Scenarios**:
  ```
  Scenario: Unified detector
    Tool: Bash (python -c)
    Steps:
      1. from elfie.brain.emotion.detector import EmotionDetector
      2. detector = EmotionDetector()
      3. inp = detector.detect({'type': 'text', 'content': '你好', 'event_id': 'e1'})
      4. assert inp.emotion in ['happiness', 'calm']
    Expected Result: 统一接口工作正常
    Evidence: .sisyphus/evidence/task-17-unified.log
  ```

  **Commit**: YES
  - Message: `feat(emotion): add ML-based emotion detectors (optional)`
  - Files: detector/
  - Pre-commit: `python -m pytest test/`

---

## Final Verification Wave

- [ ] F1. **Plan Compliance Audit** — `oracle`
- [ ] F2. **Code Quality Review** — `unspecified-high`
- [ ] F3. **Real Manual QA** — `unspecified-high`
- [ ] F4. **Scope Fidelity Check** — `deep`

---

## Commit Strategy

- **After Wave 1**: `fix(emotion): repair broken imports and add emotion types`
- **After Wave 2**: `feat(emotion): implement saturation growth and phased decay`
- **After Wave 3**: `feat(emotion): integrate new emotion system`
- **After Wave 4**: `feat(emotion): add ML-based emotion detectors`

---

## Success Criteria

### Verification Commands
```bash
# All tests pass
python -m pytest test/ -v

# Main runs without errors
python main.py

# Performance test
python -c "
import time
from elfie.brain.emotion import EmotionSystem
system = EmotionSystem()
start = time.time()
for i in range(1000):
    system.update('fear', intensity=0.5, event_id=f'e{i}')
print(f'1000 updates: {time.time()-start:.3f}s')
"
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass
- [ ] Performance < 100ms for 1000 updates
