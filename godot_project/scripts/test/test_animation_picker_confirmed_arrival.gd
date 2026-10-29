extends SceneTree
const TIMING := preload("res://runtime/lab/estate_platform_cycle.gd")

func _initialize() -> void: call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func run() -> void:
	var host := preload("res://runtime/lab/estate_animation_picker.gd").new()
	root.add_child(host)
	await process_frame
	await process_frame
	var runner: Node3D = host.runner
	var original: Node3D = runner.get("confirmed_arrival")
	if not require(original != null, "Arrival must reuse the confirmed event review, not the chair/tour actor"): return
	var body: ElfieActor = runner.get("_actor")
	var cycle: Node3D = original.get("platform_cycle")
	if not require(body == cycle.get_node("LocalPlatformBody") and body.get_script() == preload("res://characters/shared/elfie_actor.gd"), "Arrival must use the original single platform body and its animation runtime"): return
	if not require(bool(original.get("arrival_lighting").get("night")), "Confirmed arrival night lighting is missing"): return
	var environment := original.get_node("WorldEnvironment") as WorldEnvironment
	if not require(is_equal_approx(environment.environment.ambient_light_energy, 0.28), "Arrival ambient lighting differs from the confirmed night preview"): return
	var camera: Camera3D = runner.get("_camera")
	var view: Dictionary = (original.get("views") as Array)[1]
	if not require(camera.global_position.is_equal_approx(view["camera"]) and is_equal_approx(camera.fov, 100.0), "Arrival must start at the fixed rooftop front camera"): return
	var fixed := camera.global_transform
	var facing := body.global_basis.z.normalized()
	var direction: Vector3 = cycle.get("stair_target") - body.global_position
	direction.y = 0
	if not require(facing.dot(direction.normalized()) > 0.99 and body.global_position.y > 9.0, "Arrival must start on the rooftop facing the two small steps"): return
	# Hold the playback clock while inspecting exact phases. The original actor
	# still advances, so this also catches unintended heading controllers.
	runner.set("_paused", true)
	var beam := original.get("effects").get_node("ArrivalEffect/ArrivalBeam") as MeshInstance3D
	cycle.call("sample",2.5)
	if not require(not beam.visible and not body.visible, "Preparation must light the apparatus without beam, resident or rotation"): return
	var light: Node3D = original.get("arrival_lighting")
	var charge: Node3D = light.get("petal_charge")
	if not require(charge!=null,"Missing broad petal charge, moving inner carrier and three-way convergence"): return
	if not require(charge.get("shells").size()==3 and charge.get("streams").size()==3,"Charge must cover all three shell sides and provide exactly three inward streams"): return
	for stream: MeshInstance3D in charge.get("streams"):
		if not require(stream.mesh.surface_get_material(0)!=null,"Procedural energy streams must retain their own surface material through teardown"): return
	var base: MeshInstance3D
	var steps: MeshInstance3D
	for mesh: MeshInstance3D in original.get("review_geometry").find_children("*","MeshInstance3D",true,false):
		var assembly := str((mesh.get_meta("extras",{}) as Dictionary).get("assembly",""))
		if assembly=="roof01_platform": base=mesh
		if assembly=="roof01_steps": steps=mesh
	var base_rest := base.global_transform
	var steps_rest := steps.global_transform
	if not require(charge.get("spin_turns")!=null,"Missing continuous full-turn charge controller"): return
	var previous_turns := 0.0
	for seconds: float in [3.2,4.2,5.2,6.2,7.2,7.75]:
		cycle.call("sample",seconds)
		var turns := float(charge.get("spin_turns"))
		if not require(turns>previous_turns and turns<2.0,"Charge must turn continuously in one direction for two full revolutions, without rocking back"): return
		previous_turns=turns
		if not require(base.global_transform.is_equal_approx(base_rest) and steps.global_transform.is_equal_approx(steps_rest),"Outer base and steps must stay fixed during charge rotation"): return
	cycle.call("sample",8.2)
	if not require(is_equal_approx(float(charge.get("spin_turns")),2.0),"Charge assembly must finish exactly two turns before convergence"): return
	if not require(is_zero_approx(float(charge.get("rotation_angle"))) and charge.get("core").visible,"Petals must return home and form the central energy core before beam activation"): return
	for stream: MeshInstance3D in charge.get("streams"):
		if not require(stream.visible,"All three energy streams must converge before beam activation"): return
	for shell: Dictionary in charge.get("shells"):
		if not require(float(shell["material"].get_shader_parameter("fill"))>0.99,"Every broad petal side must charge all the way from tip to root"): return
	cycle.call("sample",2.5)
	if not require(light.get("petal_lights").size()==3,"Each petal needs a bounded local charge light so side petals remain legible from the fixed front view"): return
	for binding: Dictionary in light.get("bindings"):
		if str(binding["group"]).begins_with("top_"):
			var material := binding["material"] as ShaderMaterial
			if not require(is_zero_approx(float(material.get_shader_parameter("sequence_amount"))),"All ceiling rings must remain stationary while preparation lights them"): return
	var petals: Array[MeshInstance3D] = []
	var transforms: Array[Transform3D] = []
	for mesh: MeshInstance3D in original.get("review_geometry").find_children("*","MeshInstance3D",true,false):
		if str((mesh.get_meta("extras",{}) as Dictionary).get("assembly","")).begins_with("roof01_petal_"):
			petals.append(mesh)
			transforms.append(mesh.global_transform)
	cycle.call("sample",TIMING.PREPARE_SECONDS+2.0)
	var forming := float((beam.material_override as ShaderMaterial).get_shader_parameter("formation"))
	if not require(beam.visible and forming>0.0 and forming<1.0 and not body.visible,"Beam must expand from the converged core before the body starts descending"): return
	cycle.call("sample",TIMING.PREPARE_SECONDS+2.9)
	if not require(float((beam.material_override as ShaderMaterial).get_shader_parameter("formation"))>0.99 and not body.visible,"Beam must be complete before materialization"): return
	for seconds: float in [TIMING.PREPARE_SECONDS+3.35,TIMING.PREPARE_SECONDS+4.8,TIMING.ARRIVAL_END,TIMING.WALK_START+2.0,TIMING.SETTLED_AT,TIMING.REVIEW_END]:
		cycle.call("sample", seconds)
		await process_frame
		if not require(camera.global_transform.is_equal_approx(fixed) and body.global_basis.z.normalized().dot(facing) > 0.99, "Arrival camera/actor heading changed during descent or walk-down"): return
	for index in range(petals.size()):
		if not require(petals[index].global_transform.is_equal_approx(transforms[index]),"Petals must stop at the original orientation before the resident walks down"): return
	if not require(cycle.get("animation_stage") == "settled" and body.visible, "Arrival must finish visible on the rooftop floor without departure or looping"): return
	if not require(not charge.get("core").visible and is_zero_approx(float(charge.get("rotation_angle"))),"Core must dissipate and rotating assembly must remain home after arrival"): return
	for stream: MeshInstance3D in charge.get("streams"):
		if not require(not stream.visible,"Inward streams must not remain over the visible resident"): return
	for lamp: OmniLight3D in light.get("petal_lights").values():
		if not require(not lamp.visible and is_zero_approx(lamp.light_energy) and lamp.omni_range<=1.25,"Petal charge lights must remain local and switch off after arrival"): return
	runner.set("_paused", false)
	Engine.time_scale=8.0
	for frame in range(600):
		await process_frame
		if runner.completed: break
	if not require(runner.completed and cycle.get("animation_stage") == "settled", "Full arrival playback did not finish on its own"): return
	Engine.time_scale=1.0
	var old := runner
	host.select_animation(0)
	await process_frame
	await process_frame
	if not require(not is_instance_valid(old) and host.preview.get_child_count() == 1, "Replaying arrival retained the old body or fixture"): return
	host.toggle_pause()
	if not require(host.runner.process_mode == Node.PROCESS_MODE_DISABLED, "Arrival must remain pausable"): return
	host.free()
	await process_frame
	print("PASS arrival: roof chase, broad side charge, two continuous leaf/carrier turns with fixed base/steps, three-way core convergence, beam before descent, original actor/camera/walk-down, replay/pause")
	quit(0)
