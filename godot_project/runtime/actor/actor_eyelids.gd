extends RefCounted
## Progressive authored lids; each sample replaces all four weights.
const SHAPES := [
	"Sleep_EyesQuarter", "Sleep_EyesHalf",
	"Sleep_EyesThreeQuarter", "Sleep_EyesClosed",
]
var _bindings: Array[Dictionary] = []
var _owner: Node

func bind(visual: Node3D) -> void:
	reset()
	_bindings.clear()
	for mesh: MeshInstance3D in visual.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null:
			continue
		var indices := PackedInt32Array()
		for shape_name: String in SHAPES:
			indices.append(mesh.find_blend_shape_by_name(StringName(shape_name)))
		if not indices.has(-1):
			_bindings.append({"mesh": mesh, "indices": indices})
	_write(0.0)

func acquire(owner: Node) -> void:
	reset()
	_owner = owner

func sample(owner: Node, amount: float) -> void:
	if is_instance_valid(_owner) and owner == _owner:
		_write(amount)

func release(owner: Node) -> void:
	# An old controller may exit after its replacement has already acquired lids.
	if owner == _owner:
		reset()

func reset() -> void:
	_write(0.0)
	_owner = null

func _write(amount: float) -> void:
	var value := clampf(amount, 0.0, 1.0) if is_finite(amount) else 0.0
	for binding: Dictionary in _bindings:
		var mesh := binding["mesh"] as MeshInstance3D
		if not is_instance_valid(mesh):
			continue
		var indices: PackedInt32Array = binding["indices"]
		for index in range(SHAPES.size()):
			var weight := maxf(0.0, 1.0 - absf(value * 4.0 - float(index + 1)))
			mesh.set_blend_shape_value(indices[index], weight)
