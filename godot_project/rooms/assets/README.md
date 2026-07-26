# Room component assets

> 中文版：[`README_zh.md`](README_zh.md)

`rooms/assets/` holds only the components and visual assets used to assemble
rooms — no characters, and no complete room layouts.

- `beds/`: beds and bedside components, as `.tscn`.
- `chairs/`, `tables/`, `storage/`: chairs, tables, bookshelves and other
  furniture components, as `.tscn`.
- `exercise/`, `instruments/`, `teleporter/`: functional room components;
  models as `.glb`, Godot compositions as `.tscn`.
- `materials/`: reusable materials and textures; materials as `.tres`,
  textures preferably as `.png` or `.webp`.
- `themes/`: room color palettes and theme configuration.
- `artwork/gallery/`: an image library usable for wallpaper, murals and
  picture frames; photos as `.jpg`, images needing an alpha channel as `.png`
  or `.webp`.
- `reference/`: for reference only while authoring and aligning components; not
  part of runtime room assembly.

The `.import` files next to images and models are managed by Godot. When moving
source files, move them together and re-import; do not hand-edit the cached
files under `.godot/imported/`.
