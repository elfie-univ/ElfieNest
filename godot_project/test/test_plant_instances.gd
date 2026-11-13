extends SceneTree

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var binder = preload("res://nest/assembly/glb_placement.gd").new()
	binder.library = load("res://nest/furniture/shared/main/main-planters.glb")
	binder.source_nodes = PackedStringArray(["part_00007", "part_00013", "part_00017", "part_00001", "part_00024", "part_00025"])
	for name: String in binder.source_nodes:
		var target := MeshInstance3D.new()
		target.name = name
		binder.add_child(target)
	if not binder.bind_meshes():
		push_error("Shared leaves must bind in the formal assembly")
		binder.free(); quit(1); return
	var expected := [312, 312, 1424, 40, 56, 28]
	for index: int in expected.size():
		var target: Node = binder.get_child(index)
		var count := 0
		var batches := target.find_children("*", "MultiMeshInstance3D", true, false)
		for batch: MultiMeshInstance3D in batches:
			count += batch.multimesh.instance_count
			for i: int in batch.multimesh.instance_count:
				if not batch.multimesh.get_instance_transform(i).is_finite():
					push_error("Non-finite leaf transform"); binder.free(); quit(1); return
		if count != expected[index] or batches.size() >= count:
			push_error("Leaf instance count or actual mesh sharing differs: " + str(index) + " count=" + str(count))
			binder.free(); quit(1); return
	binder.free()
	print("PASS 2048 fine leaves, 20 broad leaves and 28 rubber leaves with paired veins bind as shared GPU batches")
	quit(0)
