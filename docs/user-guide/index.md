# User Guide

This is the user manual that goes from "building a Nest" to "meeting your first
Elfie". You can read it in order or jump straight to the section you need.

## The path

```text
Install environment → Configure data & models → Start the Nest → Meet an Elfie → Troubleshoot
```

### 1. [Install & environment](./install)

Get Git, uv and the pinned CPython 3.9.25 environment, and install the code on
your computer.

### 2. [Configure models & data](./configuration)

Understand `ELFIE_HOME`, local configuration, model providers and data
directories — and know which configuration should stay on your machine.

### 3. [Run your first Nest](./run)

Start the minimal running pipeline and verify that the environment clock, Elfie
perception and output routing are all connected.

### 4. [Troubleshooting](./troubleshooting)

Locate installation, port, model, data-directory and Godot connection issues by
symptom.

### 5. [FAQ](./faq)

Answers to questions like "What is an Elfie?", "What does the Nest store?" and
"Can it run without Ollama?".

## Scope of this manual

This manual covers how to *use* ElfieNest; it does not cover internal module
implementations, test commands or the Godot development flow. To read code,
debug modules or build the runtime, head to the [Developer docs](/developer/).

Sections without screenshots keep their text and operation paths for now;
formal UI screenshots will be added after the corresponding features are
completed and accepted.
