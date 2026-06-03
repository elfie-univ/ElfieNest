# 情绪持续时间追踪与无聊定义分析

> **日期**: 2025-06-02  
> **问题**: 是否需要情绪持续时间追踪？无聊如何定义？

---

## 一、当前实现分析

### 1.1 情绪持续时间追踪 - ❌ 未实现

**当前状态**:
```python
# EmotionSystem只存储当前值
self.emotions: Dict[str, float] = {
    "happiness": 50.0,
    "sadness": 10.0,
    # ... 没有时间戳
}
```

**缺失**:
- ❌ 没有记录情绪开始时间
- ❌ 没有记录情绪持续时间
- ❌ 无法判断"愤怒持续了1小时"
- ❌ 无法判断"平静持续了1天"（无聊）

**当前机制**:
- 使用半衰期(half-life)间接处理时间衰减
- 例如：boredom的half_life = 600秒（10分钟衰减一半）
- 但这只是衰减速度，不是持续时间

---

### 1.2 无聊(boredom)的定义 - 当前是独立情绪

**当前实现**:
```python
"boredom": {
    "base_delta": 5,
    "baseline": 20,        # 基线值较高
    "half_life": 600,      # 最长半衰期（衰减最慢）
    "max_value": 100,
}
```

**问题**: 无聊是独立情绪类型，需要手动增加boredom值

---

## 二、你的建议分析

### 2.1 无聊 = 所有情绪低 + 持续时间长？

**你的理解完全正确！**

心理学定义：
- **无聊(Boredom)** = 低唤醒(Low Arousal) + 负面效价(Negative Valence)
- 本质上是一种"缺乏刺激"的状态

**实现方案**:

#### 方案A: 计算型无聊（推荐）

```python
def calculate_boredom(self) -> float:
    """基于所有情绪低值 + 持续时间计算无聊度"""
    
    # 1. 检查所有主动情绪是否都低
    active_emotions = ['happiness', 'anger', 'fear', 'surprise', 'sadness', 'disgust']
    all_low = all(
        self.emotions[e] < 20 for e in active_emotions
    )
    
    # 2. 如果所有情绪低，检查持续时间
    if all_low:
        # 计算平静持续时间（秒）
        calm_duration = self.get_calm_duration()
        
        # 持续时间越长，无聊度越高
        # 例如：平静10分钟 → 无聊度30
        #       平静1小时 → 无聊度60
        #       平静1天 → 无聊度90
        boredom = min(90, 30 * (calm_duration / 600))  # 600秒=10分钟
        return boredom
    
    return 0.0  # 有活跃情绪，不无聊
```

**优点**:
- ✅ 符合心理学定义
- ✅ 不需要单独的boredom情绪类型
- ✅ 自动计算，无需手动触发

**缺点**:
- ⚠️ 需要实现持续时间追踪
- ⚠️ 计算逻辑稍复杂

---

#### 方案B: 保留独立boredom + 持续时间触发

```python
def tick(self, dt: float):
    """时间推进"""
    # ... 原有衰减逻辑
    
    # 检查是否触发无聊
    if self.is_all_emotions_low():
        # 平静持续时间增加
        self.calm_duration += dt
        
        # 持续平静超过阈值，增加无聊
        if self.calm_duration > 600:  # 10分钟
            self.emotions['boredom'] += 5 * (dt / 60)  # 每分钟+5
    else:
        # 有活跃情绪，重置平静持续时间
        self.calm_duration = 0
```

**优点**:
- ✅ 实现简单
- ✅ 保留当前架构

**缺点**:
- ⚠️ 仍需要boredom情绪类型
- ⚠️ 需要添加持续时间追踪

---

### 2.2 情绪持续时间追踪

**建议实现**:

```python
class EmotionSystem:
    def __init__(self):
        # 当前情绪值
        self.emotions: Dict[str, float] = {...}
        
        # 新增：情绪持续时间追踪
        self.emotion_durations: Dict[str, float] = {
            name: 0.0 for name in EMOTION_CONFIGS
        }
        
        # 新增：平静持续时间（所有情绪低）
        self.calm_duration: float = 0.0
        
        # 新增：上次更新时间
        self.last_tick_time: float = time.time()
    
    def tick(self, dt: float):
        """时间推进"""
        # 1. 应用衰减
        for name in self.emotions:
            old_value = self.emotions[name]
            new_value = decay(old_value, dt, ...)
            self.emotions[name] = new_value
            
            # 2. 更新持续时间
            if abs(new_value - old_value) < 0.1:
                # 情绪值变化小，持续时间增加
                self.emotion_durations[name] += dt
            else:
                # 情绪值变化大，重置持续时间
                self.emotion_durations[name] = 0.0
        
        # 3. 更新平静持续时间
        if self.is_all_emotions_low():
            self.calm_duration += dt
        else:
            self.calm_duration = 0.0
    
    def is_all_emotions_low(self, threshold: float = 20.0) -> bool:
        """检查所有情绪是否都低于阈值"""
        return all(
            self.emotions[e] < threshold 
            for e in self.emotions 
            if e != 'boredom'  # 排除boredom本身
        )
    
    def get_emotion_duration(self, emotion: str) -> float:
        """获取情绪持续时间（秒）"""
        return self.emotion_durations.get(emotion, 0.0)
    
    def get_calm_duration(self) -> float:
        """获取平静持续时间（秒）"""
        return self.calm_duration
```

---

### 2.3 情绪可配置

**建议实现**:

#### Step 1: 创建配置文件

```yaml
# config/emotions.yaml
emotions:
  happiness:
    baseline: 50
    half_life: 300
    base_delta: 20
    max_value: 100
    accumulate_rate: 0.5
    decay_high_multiplier: 0.3
    decay_low_multiplier: 3.0
    decay_threshold: 50.0
    frequency_slow_coefficient: 0.5
  
  sadness:
    baseline: 10
    half_life: 300
    base_delta: 20
    # ...
  
  # 可以添加新情绪
  curiosity:
    baseline: 30
    half_life: 180
    base_delta: 15
    # ...

# 情绪交互规则
interactions:
  - source: fear
    target: anger
    type: transfer
    threshold: 70
    rate: 0.1
  
  - source: happiness
    target: anger
    type: inhibition
    rate: 0.3
```

#### Step 2: 修改加载逻辑

```python
# emotion_types.py
import yaml
from pathlib import Path

def load_emotion_configs(config_path: str = None) -> Dict[str, Any]:
    """从YAML加载情绪配置"""
    if config_path and Path(config_path).exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            return config.get('emotions', {})
    
    # 默认配置（硬编码）
    return DEFAULT_EMOTION_CONFIGS

# 使用
EMOTION_CONFIGS = load_emotion_configs("config/emotions.yaml")
```

---

## 三、简化方案（推荐）

### 最小改动方案

**只添加持续时间追踪**，不改变其他架构：

```python
class EmotionSystem:
    def __init__(self):
        # 原有属性
        self.emotions: Dict[str, float] = {...}
        
        # 新增：平静持续时间
        self.calm_duration: float = 0.0
    
    def tick(self, dt: float):
        """时间推进"""
        # 原有衰减逻辑
        # ...
        
        # 新增：更新平静持续时间
        if self.is_all_emotions_low():
            self.calm_duration += dt
            
            # 平静超过10分钟，自动增加无聊
            if self.calm_duration > 600:
                self.emotions['boredom'] = min(100, 20 + self.calm_duration / 60)
        else:
            self.calm_duration = 0
    
    def is_all_emotions_low(self) -> bool:
        """检查所有情绪是否都低"""
        threshold = 20.0
        return all(
            self.emotions[e] < threshold
            for e in ['happiness', 'anger', 'fear', 'surprise', 'sadness', 'disgust']
        )
```

**优点**:
- ✅ 最小改动
- ✅ 无聊自动计算
- ✅ 保留当前架构

---

## 四、建议

### 建议1: 实现持续时间追踪（必要）

添加`calm_duration`字段，追踪平静持续时间。

### 建议2: 无聊自动计算（推荐）

平静超过10分钟 → 自动增加无聊度

### 建议3: 情绪可配置（可选）

创建`config/emotions.yaml`，支持动态添加情绪。

### 建议4: 移除attachment（可选）

依恋是复杂社会情绪，可以移除。

---

## 五、总结

| 问题 | 当前状态 | 建议 |
|------|---------|------|
| 持续时间追踪 | ❌ 未实现 | ✅ 添加calm_duration |
| 无聊定义 | 独立情绪 | ✅ 自动计算（平静+持续时间） |
| 情绪可配置 | ❌ 硬编码 | ⚠️ 可选（创建YAML配置） |

**核心建议**: 添加持续时间追踪，无聊自动计算，系统更简洁。
