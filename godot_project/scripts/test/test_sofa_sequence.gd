extends SceneTree

var failures: Array[String] = []


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	var review := preload("res://runtime/lab/sofa_world_review.gd").new()
	var nest := Node3D.new()
	var characters := Node3D.new()
	root.add_child(nest)
	root.add_child(characters)
	root.add_child(review)
	await review.setup(nest, characters)
	if not String(review.get("_phase")).begins_with("READY"):
		push_error(String(review.get("_phase")))
		quit(1)
		return
	review.stage_reached.connect(func(title: String) -> void:
		var audit := preload("res://scripts/test/chair_skin_contact_audit.gd").sample(review.get("_actor"), null)
		print("SOFA_SKIN_CONTACT ", title, " ", audit)
		if not audit.is_empty(): failures.append(title))
	review.call("_run_trial")
	var previous := ""
	var frames := 0
	while bool(review.get("_running")) and frames < 6000:
		await physics_frame
		frames += 1
		var phase := String(review.get("_phase"))
		if phase != previous:
			print("SOFA_PHASE ", phase)
			previous = phase
	var final := String(review.get("_phase"))
	print("SOFA_RESULT ", final, " skin_failures=", failures)
	var accepted := final.begins_with("SOFA TRIAL ENDED") and failures.is_empty()
	review.queue_free()
	characters.queue_free()
	nest.queue_free()
	await process_frame
	quit(0 if accepted else 1)
