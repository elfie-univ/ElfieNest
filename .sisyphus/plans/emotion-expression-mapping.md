# 情绪表达映射实现计划

> **版本**: v1.0  
> **日期**: 2025-06-02  
> **目标**: 实现情绪→表达映射，让精灵的情绪能够通过表情、动作、语音外化

---

## TL;DR

> **目标**: 实现情绪表达映射系统
> 
> **核心改动**:
> - 新建emotion_expressions.yaml配置文件
> - 新建expression_mapper.py映射逻辑
> - 在GodotAPI添加send_expression()方法
> - 在EmotionSystem添加get_expression()方法
> 
> **预计工作量**: Medium (5-8小时)
> **并行执行**: NO (顺序实现)
> **关键路径**: 配置文件 → 映射逻辑 → EmotionSystem集成 → Godot集成 → 测试验证

---

## 一、设计依据

### 1.1 架构分析

**当前状态**:
- ✅ EmotionSystem可以计算情绪值
- ✅ GodotAPI已实现WebSocket通信
- ✅ MotionActuator已支持基础动作
- ❌ 缺少情绪→表达的自动映射

**目标**:
- 情绪系统能够自动驱动精灵的表情、动作、语音
- 对接Godot 3D，实现情绪可视化

---

## 二、实现方案

### Phase 1: 配置文件和映射引擎

#### Task 1: 创建情绪表达映射配置

**文件**: `elfie/config/emotion_expressions.yaml` (新建)

**内容**:
```yaml
# 情绪表达映射配置
# 定义每种情绪触发的表情、动作、语音语气

emotions:
  happiness:
    expression: "happy_face"
    actions:
      low: ["wag_tail"]           # 值20-40
      medium: ["wiggle_ears"]     # 值40-70
      high: ["jump", "wag_tail"]  # 值70+
    voice_modifier: "cheerful"
    threshold: 30
    
  sadness:
    expression: "sad_face"
    actions:
      low: ["droop_head"]
      medium: ["slow_movement"]
      high: ["droop_head", "slow_movement"]
    voice_modifier: "sorrowful"
    threshold: 40
    
  anger:
    expression: "angry_face"
    actions:
      low: ["shake_head"]
      medium: ["stomp"]
      high: ["shake_head", "stomp"]
    voice_modifier: "firm"
    threshold: 40
    
  fear:
    expression: "fearful_face"
    actions:
      low: ["tremble"]
      medium: ["hide"]
      high: ["tremble", "hide"]
    voice_modifier: "nervous"
    threshold: 35
    
  surprise:
    expression: "surprised_face"
    actions:
      low: ["blink_eyes"]
      medium: ["jump"]
      high: ["jump", "blink_eyes"]
    voice_modifier: "excited"
    threshold: 30
    
  disgust:
    expression: "disgusted_face"
    actions:
      low: ["shake_head"]
      medium: ["step_back"]
      high: ["shake_head", "step_back"]
    voice_modifier: "disgusted"
    threshold: 45

# 默认表达（无强烈情绪时）
default_expression:
  expression: "neutral_face"
  actions: []
  voice_modifier: "neutral"
```

#### Task 2: 创建映射引擎

**文件**: `elfie/brain/emotion/expression_mapper.py` (新建)

**核心功能**:
- 从YAML加载映射配置
- 根据情绪值和强度返回表达参数
- 处理主导情绪选择

---

### Phase 2: EmotionSystem集成

#### Task 3: 在EmotionSystem添加get_expression()方法

**文件**: `elfie/brain/emotion/emotion_system.py`

**改动**:
```python
def get_expression(self) -> dict:
    """获取当前情绪的表达参数
    
    Returns:
        dict: {
            "expression": str,
            "actions": list,
            "voice_modifier": str,
            "intensity": float,
            "emotion": str
        }
    """
    from .expression_mapper import ExpressionMapper
    mapper = ExpressionMapper()
    return mapper.get_expression_for_emotions(self.emotions)
```

---

### Phase 3: Godot集成

#### Task 4: 在GodotAPI添加send_expression()方法

**文件**: `elfienest/godot_api.py`

**改动**:
```python
def send_expression(self, expression_data: dict):
    """发送情绪表达事件到Godot
    
    Args:
        expression_data: 表达参数，包含expression, actions, voice_modifier等
    """
    self.send_action("emotion_expression", expression_data)
```

---

### Phase 4: ElfieIndividual集成

#### Task 5: 在ElfieIndividual的tick()中集成表达映射

**文件**: `elfie/elfie_individual.py`

**改动**: 在tick()方法末尾添加:
```python
# 检查情绪变化，发送表达事件
if hasattr(self, 'emotion_system') and self.emotion_system:
    expression = self.emotion_system.get_expression()
    if expression:
        self._send_emotion_expression(expression)
```

---

### Phase 5: 测试验证

#### Task 6: 创建单元测试

**文件**: `test/test_expression_mapper.py` (新建)

**测试内容**:
- 配置加载测试
- 强度阈值测试
- 主导情绪选择测试
- 边界情况测试

#### Task 7: 集成测试

**验证**:
- 运行主程序，检查表达事件是否正确发送
- 检查Godot是否能接收到emotion_expression事件

---

## 三、TODOs

- [ ] 1. 创建emotion_expressions.yaml配置文件

  **What to do**:
  - 创建 `elfie/config/emotion_expressions.yaml`
  - 定义6种情绪的表达映射
  - 定义默认表达
  
  **Must NOT do**:
  - 不要定义过于复杂的动作列表
  
  **Commit**: YES - message: `feat(emotion): 添加情绪表达映射配置`

- [ ] 2. 创建expression_mapper.py映射引擎

  **What to do**:
  - 创建 `elfie/brain/emotion/expression_mapper.py`
  - 实现ExpressionMapper类
  - 实现get_expression_for_emotions()方法
  - 处理强度阈值逻辑
  
  **Commit**: NO (和Task 1一起提交)

- [ ] 3. 在EmotionSystem添加get_expression()方法

  **What to do**:
  - 编辑 `elfie/brain/emotion/emotion_system.py`
  - 添加get_expression()方法
  - 导入ExpressionMapper
  
  **Commit**: NO (和Task 1一起提交)

- [ ] 4. 在GodotAPI添加send_expression()方法

  **What to do**:
  - 编辑 `elfienest/godot_api.py`
  - 添加send_expression()方法
  
  **Commit**: NO (和Task 1一起提交)

- [ ] 5. 在ElfieIndividual集成表达映射

  **What to do**:
  - 编辑 `elfie/elfie_individual.py`
  - 在tick()中调用get_expression()
  - 发送表达事件到Godot
  
  **Commit**: NO (和Task 1一起提交)

- [ ] 6. 创建单元测试

  **What to do**:
  - 创建 `test/test_expression_mapper.py`
  - 测试配置加载、强度阈值、主导情绪选择
  
  **Commit**: NO (和Task 1一起提交)

- [ ] 7. 运行测试验证

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
- ✅ EmotionSystem.get_expression()可用
- ✅ 表达事件能发送到Godot

---

## 五、Commit策略

- **1**: `feat(emotion): 实现情绪表达映射系统`
  - Files: emotion_expressions.yaml, expression_mapper.py, emotion_system.py, godot_api.py, elfie_individual.py, test_expression_mapper.py

---

## 六、成功标准

- [ ] 配置文件创建完成
- [ ] ExpressionMapper类实现完成
- [ ] EmotionSystem集成完成
- [ ] GodotAPI扩展完成
- [ ] ElfieIndividual集成完成
- [ ] 测试全部通过
- [ ] 表达事件能正确发送
