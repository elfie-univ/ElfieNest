"""从已生成的狐狸母版分批渲染指定 Shape Key 预览。"""

from __future__ import annotations

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_fox_morph_prototype import render_previews  # noqa: E402


def main() -> None:
    if "--" not in sys.argv:
        raise RuntimeError("必须在 -- 后提供需要渲染的 variant 名称")
    variants = set(sys.argv[sys.argv.index("--") + 1 :])
    if not variants:
        raise RuntimeError("variant 列表不能为空")
    mesh = max(
        (obj for obj in bpy.context.scene.objects if obj.type == "MESH"),
        key=lambda item: len(item.data.vertices),
    )
    output = Path(__file__).resolve().parents[1] / "fox/source/previews/morph_prototype"
    render_previews(mesh, output, variants)
    print("MORPH_PREVIEW_BATCH_DONE " + ",".join(sorted(variants)))


if __name__ == "__main__":
    main()
