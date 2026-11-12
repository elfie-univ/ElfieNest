extends SceneTree

func _initialize() -> void:
	var estate := preload("res://nest/assembly/estate_runtime.gd").new()
	var sun := DirectionalLight3D.new(); sun.shadow_enabled = true; estate.add_child(sun)
	var fill := DirectionalLight3D.new(); estate.add_child(fill)
	var near := DirectionalLight3D.new(); near.shadow_enabled = true
	near.directional_shadow_max_distance = 12.0
	near.directional_shadow_mode = DirectionalLight3D.SHADOW_ORTHOGONAL
	estate.add_child(near)
	if not estate.has_method("apply_web_shadow_budget"):
		push_error("Split runtime lost the original Web sun-shadow budget")
		estate.free(); quit(1); return
	estate.apply_web_shadow_budget()
	var ok: bool = sun.shadow_enabled and sun.directional_shadow_max_distance == 30.0 and sun.directional_shadow_mode == DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS and is_equal_approx(sun.directional_shadow_fade_start,0.7)
	ok = ok and not fill.shadow_enabled and fill.directional_shadow_max_distance == 100.0
	ok = ok and near.directional_shadow_max_distance == 12.0 and near.directional_shadow_mode == DirectionalLight3D.SHADOW_ORTHOGONAL
	if not ok: push_error("Web budget changed authored near shadows or unshadowed fill lights")
	estate.free()
	print("SPLIT_WEB_SHADOW_BUDGET ","PASS" if ok else "FAIL")
	quit(0 if ok else 1)
