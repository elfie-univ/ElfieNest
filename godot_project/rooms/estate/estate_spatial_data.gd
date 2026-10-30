extends Resource
## Offline-authored physical/navigation data for the one complete estate.

const FORMAT_VERSION := 3
const AUTHORITY_FORMAT_VERSION := 1
const COLLISION_POLICY := "central-structure-and-solid-furniture-v3"
const PATH := "res://rooms/estate/estate_spatial.res"
const MODEL := "res://rooms/estate/ElfieNest-complete-final.glb"
const LIGHTING := "res://rooms/estate/estate_outdoor_lighting.scn"
const INSTANCES := "res://rooms/estate/ElfieNest-complete-final.instances.bin"
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
@export var mesh_shapes: Dictionary = {}
@export var authority_scene: PackedScene
@export var authority_format_version: int = 0

static func imported_model_file() -> String:
	# Exports contain the imported scene plus .remap, not the source GLB.
	for suffix: String in [".remap",".import"]:
		if not FileAccess.file_exists(MODEL+suffix):continue
		var config := ConfigFile.new()
		if config.load(MODEL+suffix)!=OK:return ""
		return str(config.get_value("remap","path",""))
	return ""

static func current_inputs() -> Dictionary:
	# The authority pack carries hashes computed from the full exported inputs.
	# It omits only the unused display scene; stale spatial data still fails the
	# same exact comparison against the full export's geometry and layout.
	var receipt := "res://rooms/estate/authority_inputs.json"
	if FileAccess.file_exists(receipt):
		var inputs: Variant = JSON.parse_string(FileAccess.get_file_as_string(receipt))
		if not inputs is Dictionary or inputs.size() != 3: return {}
		for key: String in ["scene", "instances", "lighting"]:
			if not inputs.get(key) is String or inputs[key].length() != 64: return {}
		return inputs
	var scene := imported_model_file()
	if scene.is_empty() or not FileAccess.file_exists(scene):return {}
	return {"scene":FileAccess.get_sha256(scene),"instances":FileAccess.get_sha256(INSTANCES),"lighting":FileAccess.get_sha256(LIGHTING)}

func matches_inputs(inputs: Dictionary) -> bool:
	return (format_version==FORMAT_VERSION and collision_policy==COLLISION_POLICY and not inputs.is_empty()
		and source_inputs==inputs and navigation_settings==NAV_SETTINGS
		and navigation_scene!=null and boundary_shape!=null
		and activity_buckets.size()==6 and not mesh_shapes.is_empty()
		and raw_mask.size()==1020*1020 and connected_mask.size()==raw_mask.size())

func matches_authority_inputs(inputs: Dictionary) -> bool:
	return matches_inputs(inputs) and authority_scene != null and authority_format_version == AUTHORITY_FORMAT_VERSION
