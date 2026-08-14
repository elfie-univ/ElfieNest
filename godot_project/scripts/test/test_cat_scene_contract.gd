extends SceneTree

const CAT_SCENE := preload("res://characters/cat/cat.tscn")
const REQUIRED_ANIMATIONS := [
	"idle",
	"walking",
	"running",
	"jump",
	"twist_dance",
]


func _init() -> void:
	var cat := CAT_SCENE.instantiate()
	if cat == null or not cat is CharacterBody3D:
		push_error("Myelle scene must instantiate a CharacterBody3D")
		quit(1)
		return
	root.add_child(cat)
	await process_frame
	var visual_root := cat.get_node_or_null("VisualRoot") as Node3D
	var animation_player := cat.get_node_or_null("AnimationPlayer") as AnimationPlayer
	if visual_root == null or animation_player == null:
		push_error("Myelle scene is missing shared actor nodes")
		quit(1)
		return
	var meshes := visual_root.find_children("*", "MeshInstance3D", true, false)
	if meshes.size() < 8:
		push_error("Myelle procedural scene has too few visible parts")
		quit(1)
		return
	for animation_name: String in REQUIRED_ANIMATIONS:
		if not animation_player.has_animation(animation_name):
			push_error("Myelle scene is missing animation name: %s" % animation_name)
			quit(1)
			return
	if String(cat.get("species_id")) != "cat":
		push_error("Myelle scene species_id is not cat")
		quit(1)
		return
	cat.call("configure", "myelle-1", Vector3.ZERO, {"height": "standard", "build": "standard"})
	var bounds := cat.call("visual_bounds") as AABB
	if bounds.size.y <= 0.0:
		push_error("Myelle visual bounds were not resolved")
		quit(1)
		return
	if not bool(cat.call("play_runtime_expression", "happy")):
		push_error("Myelle shared expression contract was not accepted")
		quit(1)
		return
	if not bool(cat.call("play_preview_intent", {"type": "motion", "motion": "jump"})):
		push_error("Myelle preview motion contract was not accepted")
		quit(1)
		return
	cat.queue_free()
	print("Myelle cat scene contract passed")
	quit()
