# 情绪系统简化计划

> **版本**: v3.0  
> **日期**: 2025-06-02  
> **目标**: 简化情绪系统，只保留6种基本情绪，移除不必要的复杂度

---

## TL;DR

> **目标**: 简化情绪系统，符合科学依据
> 
> **核心改动**:
> - 移除boredom和attachment
> - 只保留6种Ekman基本情绪
> - 不实现持续时间追踪（人体都没有这个机制）
> 
> **预计工作量**: Quick (配置修改 + 测试更新)
> **并行执行**: NO (顺序修改)
> **关键路径**: 修改配置 → 更新代码 → 更新测试 → 验证

---

## 一、设计依据

### 1.1 科学依据

| 依据 | 来源 | 结论 |
|------|------|------|
| **Ekman基本情绪** | 心理学研究 | 6种基本情绪：happiness, sadness, anger, fear, surprise, disgust |
| **人体无持续时间感知** | 神经科学研究 | 激素只有当前浓度，无法感知持续时间 |
| **无聊非基本情绪** | 心理学定义 | 无聊是状态描述，可通过低唤醒度计算 |

### 1.2 简化原则

- ✅ 只保留真正的基础情绪
- ✅ 移除衍生/复杂情绪
- ✅ 不实现人体都没有的机制（持续时间追踪）
- ✅ 系统越简单越好

---

## 二、具体改动

### Wave 1: 移除boredom和attachment

#### Task 1: 修改emotion_types.py

**文件**: `elfie/brain/emotion/emotion_types.py`

**改动**:
```python
# 移除 boredom 和 attachment 的配置
EMOTION_CONFIGS = {
    "happiness": {...},
    "sadness": {...},
    "anger": {...},
    "fear": {...},
    "surprise": {...},
    "disgust": {...},
    # 移除 "boredom": {...}
    # 移除 "attachment": {...}
}
```

#### Task 2: 更新EmotionType枚举

**文件**: `elfie/brain/emotion/emotion_types.py`

**改动**:
```python
class EmotionType(Enum):
    """情绪类型 - 基于Ekman基本情绪理论"""
    HAPPINESS = "happiness"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    SURPRISE = "surprise"
    DISGUST = "disgust"
    # 移除 BOREDOM, ATTACHMENT
```

#### Task 3: 更新情绪交互配置

**文件**: `elfie/brain/emotion/emotion_types.py`

**改动**:
```python
EMOTION_INTERACTIONS = {
    # 保留
    ('fear', 'anger'): {'type': 'transfer', 'threshold': 70, 'rate': 0.1},
    ('happiness', 'anger'): {'type': 'inhibition', 'rate': 0.3},
    
    # 移除（因为attachment被移除）
    # ('sadness', 'attachment'): {'type': 'enhancement', 'rate': 0.2},
}
```

---

### Wave 2: 更新代码

#### Task 4: 更新EmotionSystem初始化

**文件**: `elfie/brain/emotion/emotion_system.py`

**改动**: 无需修改（自动从EMOTION_CONFIGS读取）

#### Task 5: 更新emotional_state.py（旧版兼容）

**文件**: `elfie/brain/emotion/emotional_state.py`

**改动**:
```python
class AmygdalaEmotionalState:
    def __init__(self):
        self.emotions = {
            "happiness": 50.0,
            "anxiety": 10.0,   # 保留（映射到fear）
            "jealousy": 0.0,   # 保留（映射到attachment，后续移除）
            # 移除 "boredom": 20.0
        }
```

---

### Wave 3: 更新测试

#### Task 6: 更新测试文件

**文件**: `test/test_emotion_system.py`, `test/test_interactions.py`

**改动**:
- 移除所有boredom和attachment相关的测试
- 更新情绪数量断言（从8改为6）

#### Task 7: 更新test_embodied_perception.py

**文件**: `test/test_embodied_perception.py`

**改动**: 检查是否有boredom/attachment引用，如有则移除

---

### Wave 4: 验证

#### Task 8: 运行测试验证

**命令**: `pytest test/ -v`

**预期**: 所有测试通过

---

## 三、TODOs

- [ ] 1. 移除boredom和attachment配置（emotion_types.py）
  
  **What to do**:
  - 编辑 `elfie/brain/emotion/emotion_types.py`
  - 从EMOTION_CONFIGS中移除boredom和attachment
  - 从EmotionType枚举中移除BOREDOM和ATTACHMENT
  - 从EMOTION_INTERACTIONS中移除涉及attachment的规则
  
  **Must NOT do**:
  - 不要修改其他情绪的配置参数
  
  **Commit**: YES - message: `refactor(emotion): 移除boredom和attachment，简化为6种基本情绪`

- [ ] 2. 更新emotional_state.py
  
  **What to do**:
  - 移除boredom字段
  
  **Commit**: NO (和Task 1一起提交)

- [ ] 3. 更新测试文件
  
  **What to do**:
  - 移除test_emotion_system.py中的boredom/attachment测试
  - 移除test_interactions.py中的attachment相关测试
  - 更新情绪数量断言（8→6）
  
  **Commit**: NO (和Task 1一起提交)

- [ ] 4. 运行测试验证
  
  **What to do**:
  - 运行 `pytest test/ -v`
  - 确保所有测试通过
  
  **Commit**: NO (验证)

---

## 四、验证策略

### 验证命令
```bash
pytest test/ -v
```

### 预期结果
- ✅ 所有测试通过
- ✅ 情绪数量 = 6
- ✅ 无boredom和attachment引用

---

## 五、Commit策略

- **1**: `refactor(emotion): 移除boredom和attachment，简化为6种基本情绪`
  - Files: emotion_types.py, emotional_state.py, test_*.py

---

## 六、成功标准

- [ ] EMOTION_CONFIGS只包含6种情绪
- [ ] EmotionType枚举只包含6种情绪
- [ ] EMOTION_INTERACTIONS不包含attachment
- [ ] 所有测试通过
- [ ] 代码更简洁，易于维护
