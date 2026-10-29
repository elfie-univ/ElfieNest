extends SceneTree
const TIMING := preload("res://runtime/lab/estate_platform_cycle.gd")
class CameraNest extends ModularNest:
	func _ready() -> void: pass
func _initialize() -> void: call_deferred("run")
func require(ok: bool, message: String) -> bool:
	if not ok: push_error(message); quit(1)
	return ok
func energy(light: Node3D, group: String) -> float:
	var value := -1.0
	for binding: Dictionary in light.get("bindings"):
		if binding["group"]==group:
			value=maxf(value,float(binding["material"].get_shader_parameter("light_level")))
	return value
func run() -> void:
	var owner := CameraNest.new()
	var hud: Node=load("res://ui/observation_hud.tscn").instantiate()
	hud.name="ObservationHUD"
	owner.add_child(hud)
	root.add_child(owner)
	var review: Node3D=load("res://runtime/lab/estate_event_review.gd").new()
	review.set("camera_owner",owner)
	root.add_child(review)
	review.set_process(false)
	review.call("apply_arrival_night")
	var cycle: Node3D=review.get("platform_cycle")
	var light: Node3D=review.get("arrival_lighting")
	var charge: Node3D=light.get("petal_charge")
	cycle.call("sample",0.0)
	var idle_fills: Array[float] = []
	for item: Dictionary in charge.get("shells"):
		idle_fills.append(float(item["inlay"].get_shader_parameter("fill")))
	if not require(charge.get("rear_lights")!=null and charge.get("rear_lights").size()==3,"All three petals must retain their original single rear light, without a full luminous back"): return
	if not require(charge.get("stream_dimensions")!=null,"Incoming energy must use the full petal height/width, not a small tube radius"): return
	var dimensions: Array=charge.get("stream_dimensions")
	if not require(dimensions.size()==3,"All three leaves must emit full-face volumes"): return
	for index in range(3):
		var shell_bounds: AABB=charge.get("shells")[index]["mesh"].global_transform*charge.get("shells")[index]["mesh"].get_aabb()
		var beam: MeshInstance3D=charge.get("streams")[index]
		if not require(beam.mesh.get_aabb().size.y>=shell_bounds.size.y*0.98 and dimensions[index].x>=0.7,"Beam must cover the entire leaf silhouette vertically and across its emitting face"): return
	if not require(charge.get("down_front")!=null,"A separate visible downward energy front must precede the resident arrival"): return
	if not require(charge.get("roof_blooms").size()>0,"The actual opaque upper ceiling must participate, not only its partly occluded skylight"): return
	for roof: MeshInstance3D in charge.get("roof_blooms"):
		if not require((roof.global_transform*roof.mesh.get_aabb()).end.y>12.0,"Roof illumination must bind actual ceiling-height geometry, not a lower floor surface"): return
	cycle.call("sample",1.8)
	if not require(light.get("stage")=="preparation","Preparation must be its own still-lighting stage"): return
	if not require(is_zero_approx(float(charge.get("spin_turns"))),"Preparation must not rotate the petals"): return
	for binding: Dictionary in light.get("bindings"):
		if str(binding["group"]).begins_with("top_"):
			if not require(is_zero_approx(float(binding["material"].get_shader_parameter("sequence_amount"))),"Ceiling must only light up during preparation"): return
	cycle.call("sample",4.5)
	if not require(light.get("stage")=="charge","Rotation must belong to the charge stage"): return
	var master := float(charge.get("rotation_angle"))
	var groups := {}
	for binding: Dictionary in light.get("bindings"):
		var group := str(binding["group"])
		groups[group]=true
		if group.begins_with("top_") or group=="platform_ring":
			if not require(absf(float(binding["material"].get_shader_parameter("spin_angle"))-master)<0.0001,"Roof, petals and platform ring must use one angular phase"): return
	for group: String in ["top_1","top_2","top_3","platform_ring","platform_disc","platform_side","steps","floor_inner","floor_outer"]:
		if not require(groups.has(group),"Missing independent light group: "+group): return
	var shell: MeshInstance3D=charge.get("shells")[0]["mesh"]
	var axis := shell.global_basis*Vector3.RIGHT
	if not require(absf(wrapf(atan2(axis.z,axis.x)-master,-PI,PI))<0.0001,"Petal geometry must turn in the same direction as the light head"): return
	if not require(energy(light,"steps")<0.15 and energy(light,"floor_inner")<0.15,"Walk guidance must not reach full brightness during charge"): return
	cycle.call("sample",8.2)
	for rear: Dictionary in charge.get("rear_lights"):
		if not require(rear["mesh"].visible and float(rear["material"].get_shader_parameter("level"))>0.1,"Original rear lines must light during charge"): return
	if not require(float(charge.get("column_height"))>=2.0,"Converged core must be a leaf-height upright column"): return
	for item: Dictionary in charge.get("shells"):
		if not require(item.has("inlay") and item["inlay"] is ShaderMaterial,"Each petal needs a continuous opaque inlay on its own shell surface"): return
	cycle.call("sample",TIMING.DOME_PEAK+0.5)
	if not require(charge.get("dome")!=null and charge.get("dome").visible,"Charging must illuminate the real dome before the resident appears"): return
	if not require(float(charge.get("dome").material_override.get_shader_parameter("level"))>0.99,"The fully illuminated dome must hold its peak before descending"): return
	if not require(not cycle.get("_body").visible,"Resident must wait until the dome charge completes"): return
	cycle.call("sample",TIMING.DOWN_SWEEP_START+0.35)
	var early_height := (charge.get("down_front") as Node3D).global_position.y
	if not require(charge.get("down_front").visible and not cycle.get("_body").visible,"The independent downward front must be visible with no resident"): return
	cycle.call("sample",TIMING.DOWN_SWEEP_END-0.15)
	if not require((charge.get("down_front") as Node3D).global_position.y<early_height-1.0 and not cycle.get("_body").visible,"The broad front must actually travel from dome to platform before arrival"): return
	cycle.call("sample",TIMING.PREPARE_SECONDS+2.0)
	var legacy_beam: MeshInstance3D=review.get("effects").get_node("ArrivalEffect/ArrivalBeam")
	if not require(legacy_beam.visible and not charge.get("down_front").visible and not cycle.get("_body").visible,"Original arrival must start after the broad front reaches the platform"): return
	cycle.call("sample",TIMING.WALK_START-0.3)
	if not require(energy(light,"steps")>0.3 and energy(light,"floor_inner")<0.15,"Step lights must prelight before the first step, ahead of floor guidance"): return
	cycle.call("sample",TIMING.WALK_START+4.1)
	if not require(energy(light,"floor_inner")>0.2 and energy(light,"floor_outer")<0.15,"Inner floor guide must receive the handoff before the outer floor ring"): return
	cycle.call("sample",TIMING.REVIEW_END+0.3)
	for index in range(idle_fills.size()):
		var item: Dictionary=charge.get("shells")[index]
		if not require(is_equal_approx(float(item["inlay"].get_shader_parameter("fill")),idle_fills[index]),"Petal surface color must return to the same unlit fill as the opening frame"): return
		if not require(is_equal_approx(float(item["material"].get_shader_parameter("fill")),idle_fills[index]),"Side light must also return to its opening state"): return
	for rear: Dictionary in charge.get("rear_lights"):
		if not require(is_zero_approx(float(rear["material"].get_shader_parameter("level"))),"Rear light must clear with the arrival effect"): return
	if not require(not charge.get("dome").visible and not charge.get("core").visible,"Dome/core effects must clear after the arrival"): return
	if not require(energy(light,"steps")<0.15 and energy(light,"floor_outer")<0.15,"Guidance must return to night baseline after the walk"): return
	cycle.call("cancel")
	review.free()
	owner.free()
	await process_frame
	print("PASS four stages: still preparation, one clockwise charge phase, continuous broad petal inlays/beams, dome peak, step-to-floor light handoff and cleanup")
	quit(0)
