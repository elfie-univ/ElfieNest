extends SceneTree
const CONTROL := preload("res://nest/estate/estate_lighting.gd")
func _initialize() -> void: call_deferred("run")
func require(ok: bool, message: String) -> bool:
	if not ok: push_error(message); quit(1)
	return ok
func run() -> void:
	var fixture := Node3D.new(); root.add_child(fixture)
	var mesh := MeshInstance3D.new(); mesh.mesh = BoxMesh.new()
	var shared := StandardMaterial3D.new()
	shared.resource_name = "Outdoor concealed warm rim lamp"
	shared.emission_enabled = true; shared.emission_energy_multiplier = 1.1
	mesh.material_override = shared
	mesh.set_meta("extras", {"outdoor_fixture_id":"test"})
	fixture.add_child(mesh)
	var owner := CONTROL.new(); owner.bind(fixture); owner.apply(false)
	if not require(is_zero_approx((mesh.get_active_material(0) as BaseMaterial3D).emission_energy_multiplier), "Day/night controls must update the effective material_override, not a hidden surface override"): return
	owner.apply(true)
	if not require(is_equal_approx((mesh.get_active_material(0) as BaseMaterial3D).emission_energy_multiplier,1.1) and is_equal_approx(shared.emission_energy_multiplier,1.1), "Night emission must restore without modifying shared source material"): return
	# The observer's optical owner must update the effective override too.
	mesh.material_override = shared
	var optical := preload("res://nest/estate/estate_lighting_sample.gd").new()
	optical.bind_m01(fixture)
	optical.apply_environment(1.0,false)
	if not require(is_zero_approx((mesh.get_active_material(0) as BaseMaterial3D).emission_energy_multiplier), "Observer daylight must control effective overrides"): return
	optical.apply_environment(0.0,true)
	if not require(is_equal_approx((mesh.get_active_material(0) as BaseMaterial3D).emission_energy_multiplier,1.1), "Observer night must restore effective emission"): return
	fixture.free()
	var estate := load("res://nest/assembly/estate.tscn").instantiate() as Node3D; root.add_child(estate)
	var ribbon := estate.find_child("WholeLakeRibbon",true,false) as MeshInstance3D
	if not require(ribbon != null and ribbon.layers != 0 and ribbon.visible,"The accepted lake guidance geometry must remain rendered"): return
	var geometry := ribbon.mesh
	owner = CONTROL.new(); owner.bind(estate)
	owner.apply(true,false,PackedStringArray(),true)
	if not require(is_equal_approx((ribbon.get_active_material(0) as BaseMaterial3D).emission_energy_multiplier,1.1),"Lake guidance must retain its authored 1.1 night intensity"):return
	owner.apply(true,true,PackedStringArray(),true)
	if not require(is_equal_approx((ribbon.get_active_material(0) as BaseMaterial3D).emission_energy_multiplier,0.275),"Quiet hours must dim rather than remove the lake guidance"):return
	owner.apply(false)
	if not require(is_zero_approx((ribbon.get_active_material(0) as BaseMaterial3D).emission_energy_multiplier) and ribbon.mesh==geometry,"Daytime may switch emission off without deleting geometry"):return
	optical = preload("res://nest/estate/estate_lighting_sample.gd").new()
	optical.bind_m01(estate)
	optical.apply_environment(0.0,true)
	if not require(is_equal_approx((ribbon.get_active_material(0) as BaseMaterial3D).emission_energy_multiplier,1.1), "Full observer night must restore lake guidance"):return
	optical.apply_environment(1.0,false)
	if not require(is_zero_approx((ribbon.get_active_material(0) as BaseMaterial3D).emission_energy_multiplier), "Full observer day must switch lake guidance off"):return
	print("PASS effective material ownership and lake guidance: day off, evening 1.1, quiet 0.275, shared geometry retained")
	estate.free();quit()
