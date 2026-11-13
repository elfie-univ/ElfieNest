extends Resource
## Offline-authored physical/navigation data for the one complete estate.

const FORMAT_VERSION := 4
const AUTHORITY_FORMAT_VERSION := 4
const COLLISION_POLICY := "split-world-geometry-and-solid-furniture-v1"
const PATH := "res://nest/spatial/estate_spatial.res"
const MODEL := "res://nest/assembly/estate.tscn"
const RECEIPT := "res://nest/assembly/runtime-inputs.json"
const SOURCE_ROOTS := ["res://nest/assembly", "res://nest/buildings", "res://nest/courtyard", "res://nest/furniture", "res://nest/rendering", "res://nest/spatial"]
const NAV_SETTINGS := {
	"agent_height":1.45,"agent_radius":0.3,"agent_max_climb":0.2,
	"agent_max_slope":45.0,"cell_size":0.1,"cell_height":0.05,
}

@export var format_version: int = FORMAT_VERSION
@export var collision_policy := ""
@export var source_inputs: Dictionary = {}
@export var navigation_settings: Dictionary = {}
@export var navigation_scene: PackedScene
@export var activity_buckets: Array[Dictionary] = []
@export var raw_mask := PackedByteArray()
@export var connected_mask := PackedByteArray()
@export var boundary_segments: Array[Dictionary] = []
@export var boundary_shape: ConcavePolygonShape3D
@export var source_names := PackedStringArray()
@export var hardscape_shape: Shape3D
@export var accessible_shapes: Dictionary = {}
@export var background_scene: PackedScene
@export var mesh_shapes: Dictionary = {}
@export var authority_scene: PackedScene
@export var authority_format_version: int = 0

static func current_inputs() -> Dictionary:
	# Authoring reads the real source tree. Exported products carry the receipt
	# validated against that tree before packaging; source GLBs are not exported.
	if FileAccess.file_exists("res://nest/buildings/main/central-building.glb"):
		return {"source_tree": source_receipt().source_tree}
	if not FileAccess.file_exists(RECEIPT): return {}
	var receipt: Variant = JSON.parse_string(FileAccess.get_file_as_string(RECEIPT))
	if not receipt is Dictionary or not receipt.get("source_tree") is String or str(receipt.source_tree).length() != 64: return {}
	return {"source_tree": receipt.source_tree}

static func source_receipt() -> Dictionary:
	var files := {}
	for directory: String in SOURCE_ROOTS: _scan_inputs(directory, files)
	var paths: Array = files.keys()
	paths.sort()
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	for path: String in paths: hash.update((path + "\t" + str(files[path]) + "\n").to_utf8_buffer())
	return {"source_tree": hash.finish().hex_encode(), "files": files}

static func _scan_inputs(directory: String, files: Dictionary) -> void:
	for name: String in DirAccess.get_directories_at(directory): _scan_inputs(directory.path_join(name), files)
	for name: String in DirAccess.get_files_at(directory):
		var path := directory.path_join(name)
		if path == RECEIPT or path == PATH: continue
		var extension := name.get_extension()
		if extension in ["gd", "glb", "scn", "tscn", "tres", "json", "png", "jpg", "jpeg", "webp", "gdshader", "gdshaderinc", "import"]:
			files[path.trim_prefix("res://")] = FileAccess.get_sha256(path)

func matches_inputs(inputs: Dictionary) -> bool:
	return (format_version==FORMAT_VERSION and collision_policy==COLLISION_POLICY and not inputs.is_empty()
		and source_inputs==inputs and navigation_settings==NAV_SETTINGS
		and navigation_scene!=null and boundary_shape!=null
		and background_scene!=null and hardscape_shape!=null
		and activity_buckets.size()==6 and not mesh_shapes.is_empty()
		and raw_mask.size()==1020*1020 and connected_mask.size()==raw_mask.size())

func matches_authority_inputs(inputs: Dictionary) -> bool:
	return matches_inputs(inputs) and authority_scene != null and authority_format_version == AUTHORITY_FORMAT_VERSION
