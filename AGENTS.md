# ElfieNest Project Guide

An embodied AI creature simulation with a three-layer brain architecture, emotional chemistry, and Godot 3D integration.

## Quick Start

```bash
# Run the main simulation (3 ticks)
python main.py
```

The simulation runs without external dependencies - if Ollama is unavailable, it gracefully falls back to a built-in lightweight simulator.

## Architecture

```
ElfieNest/
├── main.py              # Entry point - orchestrates runtime, elfie, and engine
├── elfie/               # ElfieIndividual - the creature with embodied cognition
│   ├── brain/           # Neocortex (LLM reasoning), context building
│   ├── body/            # Anatomy (biped/quadruped), somatic reflexes
│   ├── interface/       # Actuators (speech, motion), sensors, signal filters
│   └── config/          # Personality, capabilities, system limits (YAML)
├── elfienest/           # ElfieNestEngine - physics tick simulation
│   ├── engine.py        # Main loop, HTTP audio server, WebSocket API
│   ├── room.py          # Multi-creature room state management
│   └── godot_api.py     # WebSocket bridge for Godot 3D client
├── runtime/             # LLMRuntimeAgent - multi-provider LLM orchestration
│   ├── agent.py         # Main agent with tool calling loop
│   ├── config.py        # Provider configs (Ollama, OpenAI, DeepSeek, Gemini, Qwen)
│   ├── model_router.py  # Energy/complexity-based model selection
│   └── plugins/         # Tools: web_search, code_sandbox, skills_evolution
└── test/                # Unit tests for embodied perception
```

## Key Concepts

### Three-Layer Brain Architecture
1. **Neocortex (Cognition)**: LLM-based reasoning and decision making
2. **Limbic System (Core Systems)**: Emotions (amygdala), energy (hypothalamus), memory (hippocampus), context (thalamus)
3. **Body (Interface)**: Physical actuators, sensors, reflex arcs

### Main Loop Flow
1. `ElfieNestEngine.start_loop()` drives physics ticks
2. Each tick: `room.tick()` updates energy/emotion decay
3. For each active elfie: `perceive_and_respond()` triggers:
   - Brainstem reflex check (instant physical response)
   - Sensory signal filtering (noise reduction)
   - Thalamus context assembly
   - Neocortex LLM decision
   - Morphological action validation
   - Motor execution and speech synthesis

## Running Tests

```bash
python -m pytest test/
# or run individual test file
python test/test_embodied_perception.py
```

Tests require no external services - they use mock agents.

## Configuration

### LLM Runtime
- Config loaded from `runtime/runtime_config.json` (gitignored)
- Falls back to environment variables: `OLLAMA_HOST`, `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `QWEN_API_KEY`
- Default local model: `qwen3.5:0.8b` via Ollama

### Creature Configs
- `elfie/config/personality.yaml` - Big Five personality traits, speech style
- `elfie/config/capabilities.yaml` - What actions the creature can perform
- `elfie/config/system_limits.yaml` - Joint limits, energy constraints

## Godot Integration

The engine runs dual servers:
- **HTTP port 8000**: Static audio file serving (edge-tts synthesized speech)
- **WebSocket port 8765**: Real-time bidirectional communication with Godot client

When Godot connects, actions are sent as `go_to`, `speak_event` events. Without Godot, runs in terminal-only mode.

## Notes

- Comments and config files are in Chinese
- The `.elfie_memories.json` file persists episodic memories between runs
- `download_novel.py` is a standalone utility, not part of the simulation
