extends SceneTree
const HULLS := preload("res://runtime/actor/furniture_seated_collision.gd")
func _initialize() -> void:
	create_timer(25.0).timeout.connect(func() -> void: push_error("Seated regression timed out"); quit(1))
	call_deferred("run")
func require(ok: bool, message: String) -> bool:
	if not ok: push_error(message); quit(1)
	return ok
func run() -> void:
	for species: String in ["tovren","saevi"]:
		var actor := (load("res://characters/%s/%s.tscn" % [species,species]) as PackedScene).instantiate() as ElfieActor
		root.add_child(actor)
		actor.configure("skin-cache",Vector3.ZERO)
		actor.set_physics_process(false)
		actor.set_process(false)
		if species == "saevi":
			for mesh: MeshInstance3D in actor.find_children("*","MeshInstance3D",true,false):
				if mesh.skin == null or mesh.mesh == null: continue
				for surface in range(mesh.mesh.get_surface_count()):
					if not require((mesh.mesh.surface_get_format(surface)&Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)==0,"Saevi still uploads eight influence slots"): return
		for angle: float in [0.0,0.4]:
			var skeleton := actor._furniture_hips().skeleton as Skeleton3D
			var hips := int(actor._furniture_hips().bone)
			skeleton.set_bone_pose_rotation(hips,Quaternion(Vector3.UP,angle))
			var expected := reference_regions(actor,true)
			var actual := HULLS.regions(actor,true)
			for key: String in expected:
				if not require(actual.has(key) and actual[key].size()==expected[key].size(),"Skin cache lost visible vertices"): return
				for index in range(expected[key].size()):
					if not require((actual[key][index] as Vector3).distance_to(expected[key][index])<0.00002,"Skin cache changed the physical body"): return
		if not require(actor.has_meta("seated_skin_sampler"),"Seating still reclassifies every vertex on every pose"): return
		if not require(actor.get_meta("seated_skin_sampler").build_count==1,"Geometry classification must be reused across poses"): return
		actor.free()
	print("PASS exact seated skin sampling and pose-independent input reuse")
	quit(0)

func reference_regions(actor: ElfieActor, include_tail: bool = false) -> Dictionary:
	var skeleton := actor._furniture_hips()["skeleton"] as Skeleton3D
	skeleton.force_update_all_bone_transforms()
	var groups: Dictionary = {}
	var to_actor := actor.global_transform.affine_inverse()
	for instance: MeshInstance3D in actor.find_children("*", "MeshInstance3D", true, false):
		if instance.skin == null or instance.mesh == null: continue
		var skin := instance.skin
		var matrices: Array[Transform3D] = []
		var names: Array[String] = []
		var mesh_frame := skeleton.global_transform.affine_inverse() * instance.global_transform
		for bind in range(skin.get_bind_count()):
			var bone := skeleton.find_bone(skin.get_bind_name(bind)) if not skin.get_bind_name(bind).is_empty() else skin.get_bind_bone(bind)
			matrices.append(to_actor * skeleton.global_transform * skeleton.get_bone_global_pose(bone) * skin.get_bind_pose(bind) * mesh_frame)
			names.append(String(skeleton.get_bone_name(bone)))
		for surface in range(instance.mesh.get_surface_count()):
			var arrays := instance.mesh.surface_get_arrays(surface)
			var vertices := arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array
			var bones := arrays[Mesh.ARRAY_BONES] as PackedInt32Array
			var weights := arrays[Mesh.ARRAY_WEIGHTS] as PackedFloat32Array
			var stride := 8 if instance.mesh.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS else 4
			for vertex in range(vertices.size()):
				var point := Vector3.ZERO
				var dominant := ""
				var weight := 0.0
				var tail := 0.0
				for influence in range(stride):
					var index := vertex * stride + influence
					var bind := bones[index]
					point += (matrices[bind] * vertices[vertex]) * weights[index]
					if "tail" in names[bind].to_lower(): tail += weights[index]
					if weights[index] > weight:
						weight = weights[index]
						dominant = names[bind]
				var is_tail := tail >= 0.5 or "tail" in dominant.to_lower()
				if is_tail and not include_tail: continue
				var region := ("tail/" + dominant) if is_tail else HULLS._region(dominant)
				if include_tail and region.ends_with("_lower_leg_foot"):
					# Keep the empty inside of the ankle; a calf+foot hull bridges it.
					region = dominant.trim_suffix("ToeBase").trim_suffix("Foot") + "_foot" if "Foot" in dominant or "Toe" in dominant else dominant
				if not groups.has(region): groups[region] = []
				(groups[region] as Array).append(point)
	return groups
