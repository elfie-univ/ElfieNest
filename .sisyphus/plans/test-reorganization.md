# 测试文件重组计划

> **版本**: v1.0  
> **日期**: 2025-06-02  
> **目标**: 按照源代码包结构重新组织测试文件

---

## 一、当前问题

**当前结构**（扁平化，难以查找）:
```
test/
├── test_actuators.py
├── test_anatomy.py
├── test_cognition.py
├── test_deduplicator.py
├── test_embodied_perception.py
├── test_emotion_system.py
├── test_energy.py
├── test_engine.py
├── test_expression_mapper.py
├── test_interactions.py
├── test_memory.py
├── test_nest_room.py
├── test_personality.py
├── test_reflex_arc.py
├── test_runtime_agent.py
└── test_sensors.py
```

**目标结构**（镜像源代码包结构）:
```
test/
├── __init__.py
├── elfie/
│   ├── __init__.py
│   ├── brain/
│   │   ├── __init__.py
│   │   ├── emotion/
│   │   │   ├── __init__.py
│   │   │   ├── test_emotion_system.py
│   │   │   ├── test_expression_mapper.py
│   │   │   ├── test_personality.py
│   │   │   ├── test_interactions.py
│   │   │   └── test_deduplicator.py
│   │   ├── cognition/
│   │   │   ├── __init__.py
│   │   │   └── test_cognition.py
│   │   ├── memory/
│   │   │   ├── __init__.py
│   │   │   └── test_memory.py
│   │   └── energy/
│   │       ├── __init__.py
│   │       └── test_energy.py
│   ├── body/
│   │   ├── __init__.py
│   │   ├── anatomy/
│   │   │   ├── __init__.py
│   │   │   └── test_anatomy.py
│   │   └── reflex/
│   │       ├── __init__.py
│   │       └── test_reflex_arc.py
│   └── interface/
│       ├── __init__.py
│       ├── actuators/
│       │   ├── __init__.py
│       │   └── test_actuators.py
│       └── sensors/
│           ├── __init__.py
│           └── test_sensors.py
├── elfienest/
│   ├── __init__.py
│   └── test_engine.py
└── runtime/
    ├── __init__.py
    └── test_runtime_agent.py
```

---

## 二、映射关系

| 当前文件 | 目标位置 | 源代码位置 |
|---------|---------|-----------|
| test_emotion_system.py | test/elfie/brain/emotion/ | elfie/brain/emotion/emotion_system.py |
| test_expression_mapper.py | test/elfie/brain/emotion/ | elfie/brain/emotion/expression_mapper.py |
| test_personality.py | test/elfie/brain/emotion/ | elfie/brain/emotion/personality.py |
| test_interactions.py | test/elfie/brain/emotion/ | elfie/brain/emotion/interactions.py |
| test_deduplicator.py | test/elfie/brain/emotion/ | elfie/brain/emotion/fusion/deduplicator.py |
| test_cognition.py | test/elfie/brain/cognition/ | elfie/brain/cognition/*.py |
| test_memory.py | test/elfie/brain/memory/ | elfie/brain/memory/*.py |
| test_energy.py | test/elfie/brain/energy/ | elfie/brain/energy/energy.py |
| test_anatomy.py | test/elfie/body/anatomy/ | elfie/body/anatomy/*.py |
| test_reflex_arc.py | test/elfie/body/reflex/ | elfie/body/reflex/reflex_arc.py |
| test_actuators.py | test/elfie/interface/actuators/ | elfie/interface/actuators/*.py |
| test_sensors.py | test/elfie/interface/sensors/ | elfie/interface/sensors/*.py |
| test_engine.py | test/elfienest/ | elfienest/engine.py |
| test_runtime_agent.py | test/runtime/ | runtime/agent.py |
| test_embodied_perception.py | test/elfie/ | elfie/elfie_individual.py |
| test_nest_room.py | test/elfienest/ | elfienest/room.py |

---

## 三、实现步骤

### Wave 1: 创建目录结构

```bash
mkdir -p test/elfie/brain/emotion
mkdir -p test/elfie/brain/cognition
mkdir -p test/elfie/brain/memory
mkdir -p test/elfie/brain/energy
mkdir -p test/elfie/body/anatomy
mkdir -p test/elfie/body/reflex
mkdir -p test/elfie/interface/actuators
mkdir -p test/elfie/interface/sensors
mkdir -p test/elfienest
mkdir -p test/runtime
```

### Wave 2: 创建__init__.py文件

每个测试目录都需要__init__.py

### Wave 3: 移动测试文件

使用git mv保持版本历史

### Wave 4: 更新导入路径

测试文件内的import语句需要更新

### Wave 5: 验证测试通过

运行pytest确保所有测试仍然通过

---

## 四、注意事项

1. **保持__init__.py** - 每个测试目录都需要__init__.py
2. **更新导入** - 测试文件内的import路径需要调整
3. **pytest配置** - 可能需要更新pytest.ini中的testpaths
4. **保持向后兼容** - 暂时保留旧的测试文件，创建符号链接或直接移动

---

## 五、验证命令

```bash
pytest test/ -v
```

预期结果：所有306个测试通过
