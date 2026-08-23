#!/usr/bin/env python3
"""Public command entry for the Infrastructure-owned Godot Web builder."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from infrastructure.godot.artifacts.web_build import main
from scripts.godot_species_validation import run_godot_species_validation

if __name__ == "__main__":
    raise SystemExit(main(godot_runner=run_godot_species_validation))
