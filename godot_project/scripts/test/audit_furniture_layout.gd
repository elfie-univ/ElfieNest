extends SceneTree

const ACTIVITY_SCENE := preload("res://rooms/activity_room.tscn")
const G := preload("res://rooms/room_geometry.gd")
const ARCHITECTURE := ["Walls", "Walls1", "Walls2", "Walls3", "Flooring", "Carpet", "floor", "ground"]
const ROOM_NAMES := ["kitchen", "sitting", "media", "gym", "garden", "working", "music", "bookroom"]


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	var probe_root := Node3D.new()
	root.add_child(probe_root)
	for kind in range(8):
		var activity := ACTIVITY_SCENE.instantiate() as ModularActivityRoom
		activity.auto_preview = false
		probe_root.add_child(activity)
		activity.build(Color.WHITE, kind)
		await process_frame
		var generated := activity.get_node("Generated") as Node3D
		var source := generated.get_node("SourceFurniture/SourceRoom") as Node3D
		var content := _content_root(source)
		var items: Array[Dictionary] = []
		for child in content.get_children():
			var furniture := child as Node3D
			if furniture == null or not furniture.visible or ARCHITECTURE.has(String(furniture.name)):
				continue
			var bounds := G.visual_bounds_in(furniture, generated)
			if bounds.size.x < 0.03 or bounds.size.y < 0.03 or bounds.size.z < 0.03:
				continue
			items.append({"name": String(furniture.name), "bounds": bounds})
			print("SIZE\t%s\t%s\t%s\t%s" % [ROOM_NAMES[kind], furniture.name, bounds.size, bounds.position])
		for first_index in range(items.size()):
			for second_index in range(first_index + 1, items.size()):
				var first := items[first_index]
				var second := items[second_index]
				var overlap := _overlap_size(first["bounds"] as AABB, second["bounds"] as AABB)
				if overlap.x > 0.02 and overlap.y > 0.02 and overlap.z > 0.02:
					print("OVERLAP\t%s\t%s\t%s\t%s" % [ROOM_NAMES[kind], first["name"], second["name"], overlap])
		activity.queue_free()
		await process_frame
	probe_root.queue_free()
	quit(0)


func _content_root(source: Node3D) -> Node3D:
	var converted := source.get_node_or_null("convert_node") as Node3D
	if converted != null:
		return converted
	var music_room := source.get_node_or_null("Room3") as Node3D
	return music_room if music_room != null else source


func _overlap_size(first: AABB, second: AABB) -> Vector3:
	return Vector3(
		minf(first.end.x, second.end.x) - maxf(first.position.x, second.position.x),
		minf(first.end.y, second.end.y) - maxf(first.position.y, second.position.y),
		minf(first.end.z, second.end.z) - maxf(first.position.z, second.position.z)
	)
