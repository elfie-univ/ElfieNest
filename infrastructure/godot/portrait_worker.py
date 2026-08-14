"""Out-of-authority Godot renderer for static adoption portraits."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from elfie.genesis import GenesisCandidate
from elfie.profile import (
    AppearanceResolver,
    ElfieIdentity,
    ElfieProfile,
    EmbodimentProfile,
    ProfileProvenance,
)


class GodotPortraitRendererAdapter:
    """Render full-body and headshot PNG data through a separate Godot worker."""

    def __init__(
        self,
        *,
        project_root: Path | None = None,
        godot_binary: str | None = None,
        timeout_seconds: float = 45.0,
    ) -> None:
        self._project_root = project_root or Path(__file__).resolve().parents[2] / "godot_project"
        self._godot_binary = godot_binary or os.environ.get("GODOT_BIN", "")
        self._timeout_seconds = timeout_seconds

    def render(self, candidate: GenesisCandidate) -> tuple[str, str]:
        binary = self._godot_binary or shutil.which("godot4") or shutil.which("godot")
        if binary is None:
            raise RuntimeError("Godot portrait worker is unavailable")
        with tempfile.TemporaryDirectory(prefix="elfie-adoption-portrait-") as directory:
            root = Path(directory)
            input_path = root / "candidate.json"
            output_dir = root / "output"
            input_path.write_text(
                json.dumps(
                    {
                        "candidate_id": candidate.candidate_id,
                        "species_id": candidate.species_id,
                        "appearance": _appearance_payload(candidate),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            command = [
                binary,
                "--path",
                str(self._project_root),
                # Godot's headless/dummy driver cannot read a SubViewport texture;
                # portraits need the local OpenGL device used by the desktop app.
                "--rendering-method",
                "gl_compatibility",
                "--script",
                "res://scripts/tools/render_adoption_portraits.gd",
                "--",
                "--input",
                str(input_path),
                "--output-dir",
                str(output_dir),
            ]
            try:
                result = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    f"Godot portrait worker timed out after {self._timeout_seconds:g}s"
                ) from exc
            if result.returncode != 0:
                detail = (result.stderr or result.stdout).strip()
                raise RuntimeError(f"Godot portrait worker failed: {detail}")
            return (
                _data_url(output_dir / f"{candidate.candidate_id}-full.png"),
                _data_url(output_dir / f"{candidate.candidate_id}-head.png"),
            )


def _appearance_payload(candidate: GenesisCandidate) -> dict[str, object]:
    profile = ElfieProfile(
        schema_version=1,
        identity=ElfieIdentity(
            elfie_id=f"portrait-{candidate.candidate_id}",
            display_name="portrait",
            species_id=candidate.species_id,
        ),
        appearance=candidate.appearance,
        provenance=ProfileProvenance(
            generator_version="genesis-v1",
            master_seed=candidate.seed,
            appearance_seed=candidate.seed,
        ),
        embodiment=EmbodimentProfile(),
    )
    return AppearanceResolver().resolve(profile).to_payload()


def _data_url(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"Godot portrait output is missing: {path.name}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


__all__ = ("GodotPortraitRendererAdapter",)
