extends SceneTree
## Verify the four formal bedroom sets share complete furniture prototypes.

const FURNITURE := "res://nest/furniture/shared/bedroom/"
const SETS := "res://nest/furniture/sets/bedroom/"
const SHARED_PART_COUNTS := {"bed-shared": 132, "chair": 14, "bedroom-cabinet": 7,
	"bedroom-lamps": 3, "bedroom-rug": 1}

func _initialize() -> void:
	call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func run() -> void:
	var prototypes := {}
	var desks := {}
	for resident: String in ["a", "b", "c", "d"]:
		var scene := load(SETS + "bedroom-set-%s.scn" % resident) as PackedScene
		if not require(scene != null, "Formal bedroom set must load: " + resident): return
		var bedroom := scene.instantiate() as Node3D
		root.add_child(bedroom)
		var checked := {}
		for placement: Node in bedroom.get_children():
			if not placement.get("library") is PackedScene: continue
			var library: String = placement.library.resource_path
			if not library.begins_with(FURNITURE): continue
			var kind := library.get_file().get_basename()
			if kind == "bedroom-desks":
				var parts := PackedStringArray()
				for mesh: MeshInstance3D in placement.get_children():
					if not require(mesh.mesh != null and mesh.mesh.get_meta("nest_source_extras", {}).get("component_id") == "desk-top", "Desktop must use its formal prototype"): return
					var id: String = placement.source_nodes[mesh.get_index()]
					if not require(id.begins_with("desktop_" + resident + "_"), "Each set needs its own fitted desktop"): return
					parts.append(id)
				if not require(parts.size() == 2 and parts[0] != parts[1] and not desks.has(resident), "A fitted desktop must retain both parts"): return
				desks[resident] = parts
				continue
			if not SHARED_PART_COUNTS.has(kind): continue
			if not require(placement.get_child_count() == SHARED_PART_COUNTS[kind], "Incomplete furniture prototype: " + kind): return
			checked[kind] = true
			for mesh: MeshInstance3D in placement.get_children():
				var id: String = kind + "/" + placement.source_nodes[mesh.get_index()]
				if not require(mesh.mesh != null and mesh.mesh == prototypes.get(id, mesh.mesh), "Copied or missing prototype: " + id): return
				prototypes[id] = mesh.mesh
				var extras: Dictionary = mesh.get_meta("extras", {})
				if extras.has("resident") and not require(str(extras.resident).to_lower() == resident, "Furniture lost its resident binding: " + id): return
		if not require(checked.size() == SHARED_PART_COUNTS.size(), "A set lost a shared furniture asset: " + resident): return
		bedroom.free()
	if not require(desks.size() == 4, "Four fitted desktop variants are required"): return
	print("BEDROOM_COMPONENT_CONTRACT four formal sets, complete shared prototypes and four fitted desktops")
	quit()
