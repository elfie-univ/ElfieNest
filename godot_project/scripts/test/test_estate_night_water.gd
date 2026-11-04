extends SceneTree
## The original fountain water glows; rings illuminate strictly inside-out.
const DISPLAY := preload("res://rooms/estate/estate_water_display.gd")
const LIGHTING := preload("res://rooms/estate/estate_lighting_sample.gd")
func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var source := load("res://rooms/estate/estate.tscn").instantiate() as Node3D
	root.add_child(source)
	var lighting := LIGHTING.new()
	lighting.bind_m01(source)
	lighting.apply_environment(0.0, true)
	var original_meshes := source.find_children("*","MeshInstance3D",true,false).size()
	var candidate: Node3D = DISPLAY.new()
	root.add_child(candidate)
	candidate.call("bind",source,Environment.new(),false)
	var sill := candidate.get_node_or_null("SubmergedInletSill") as MeshInstance3D
	if not _require(sill != null and sill.mesh != null, "The shallow channel needs its submerged stone inlet edge"): return
	var splash := candidate.get_node_or_null("WaterfallLandingSplash") as CPUParticles3D
	if not _require(splash != null and splash.emitting and splash.mesh != null, "The waterfall needs visible landing droplets"): return
	candidate.call("sample",0.55,true)
	var strips := candidate.find_children("SpillwayEdge*", "MeshInstance3D", true, false)
	if not _require(strips.size() == 2, "The short spillway needs exactly two warm edge lights"): return
	for strip: MeshInstance3D in strips:
		var points: PackedVector3Array = strip.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
		for vertex in range(0, points.size(), 2):
			# A corner miter is longer than the strip width; its projection across
			# the flow must retain 10 cm and share the complete ring cut edge.
			var width := absf(points[vertex + 1].z - points[vertex].z)
			if not _require(is_equal_approx(width, 0.10), "Both channel guides must have the fountain rim's 10 cm width across the flow"): return
			if vertex >= 2 and not _require((points[vertex + 1] - points[vertex]).dot(points[1] - points[0]) > 0.009, "Channel guide twists at the waterfall corner"): return
		var rim := source.find_child("FountainConcealedRim", true, false) as MeshInstance3D
		var rim_material := rim.get_active_material(0) as BaseMaterial3D
		var edge_material := strip.get_active_material(0) as BaseMaterial3D
		if not _require(edge_material.emission == rim_material.emission and edge_material.albedo_color == rim_material.albedo_color and is_equal_approx(edge_material.emission_energy_multiplier, rim_material.emission_energy_multiplier), "Channel guides must match the fountain rim color and night brightness"): return
		var route: PackedVector3Array = strip.get_meta("light_route")
		if not _require(route.size() >= 2 and points.size() == route.size() * 2, "Keep only the upper-edge lamps; omit the waterfall slope and vertical returns"): return
		if not _require(absf(route[0].y-route[-1].y) < 0.1, "Channel lamps must follow the gently graded upper edge"): return
		var coping := source.find_child("ROAD REF • fountain radial limestone coping", true, false) as MeshInstance3D
		if not _require(absf(route[0].y - (coping.global_transform * coping.get_aabb()).end.y - 0.008) < 0.002, "The channel must touch the fountain rim at its real elevation"): return
		var curtain_edge := source.find_child("Continuous shallow waterfall from solid spillway crest", true, false) as MeshInstance3D
		var end_x := (curtain_edge.global_transform * curtain_edge.get_aabb()).position.x
		if not _require(absf(route[-1].x - end_x) < 0.002, "Each channel lamp must reach the waterfall lip without descending"): return
		var coping_faces := coping.mesh.get_faces()
		for point: Vector3 in route:
			for face in range(0, coping_faces.size(), 3):
				var hit: Variant = Geometry3D.segment_intersects_triangle(Vector3(point.x, 2.0, point.z), Vector3(point.x, -1.0, point.z), coping.global_transform * coping_faces[face], coping.global_transform * coping_faces[face + 1], coping.global_transform * coping_faces[face + 2])
				if hit is Vector3 and not _require(point.y >= hit.y + 0.004, "The inlet guide must remain above the real coping rather than disappear inside its stone"): return

		if not _require((strip.get_active_material(0) as BaseMaterial3D).emission_energy_multiplier > 0.0, "Spillway edge light is dark at night"): return
	if not _require(not preload("res://rooms/estate/estate_opaque.gdshader").code.contains("spillway_return"), "Remove the rejected soil-patch glow rather than hide it beneath the ribbon"): return
	var landing: Array = candidate.get("spillway_rings")
	if not _require(landing.size() == 4 and (candidate.get("spillway_materials") as Array).size() == 3, "Light the original water curtain, foam and channel, plus four landing rings"): return
	var landing_material := landing[0]["material"] as ShaderMaterial
	var first_strength := float(landing_material.get_shader_parameter("accent_strength"))
	candidate.call("sample",1.7,true)
	if not _require(not is_equal_approx(first_strength, float(landing_material.get_shader_parameter("accent_strength"))), "Landing highlights must move rather than remain a static luminous disc"): return
	if not _require(candidate.get_node_or_null("LocalSpillwayLight") == null, "Use the full water curtain, not a point lamp under the waterfall"): return
	var curtain := source.find_child("Continuous shallow waterfall from solid spillway crest", true, false) as MeshInstance3D
	var curtain_material := curtain.get_active_material(0) as ShaderMaterial
	if not _require(bool(curtain_material.get_shader_parameter("is_waterfall")) and float(curtain_material.get_shader_parameter("waterfall_glow")) > 0.0, "The entire real waterfall must have an area-based night effect"): return
	var fall_phase := float(curtain_material.get_shader_parameter("waterfall_phase"))
	candidate.call("sample", 8.0, true)
	if not _require(not is_equal_approx(fall_phase, float(curtain_material.get_shader_parameter("waterfall_phase"))), "Waterfall color and downward flow must evolve over time"): return
	if not _require(candidate.get_node_or_null("LowFountainFan")==null,"Rejected fan light geometry still exists"):return
	var lake := candidate.get("lake") as MeshInstance3D
	var lake_material := lake.get_active_material(0) as ShaderMaterial
	if not _require(float(lake_material.get_shader_parameter("accent_strength"))>0.0 and float(lake_material.get_shader_parameter("accent_strength"))<0.2,"Evening lake accent is absent or overwhelms the water"):return
	if not _require(not lake_material.shader.code.contains("night_band_strength"),"Rejected lake stripe shader remains"):return
	var rings: Array = candidate.get("fountain_rings")
	if not _require(rings.size()==5,"Need the five original pool rings, not newly generated rings"):return
	for index in range(rings.size()):
		if index>0 and not _require(float(rings[index]["radius"])>float(rings[index-1]["radius"]),"Ring order is not based on real radii"):return
		candidate.call("sample",0.55+float(index)*0.7,true)
		var active := rings[index]["material"] as ShaderMaterial
		var energy := float(active.get_shader_parameter("accent_strength"))
		if not _require(energy>1.0,"Ring never visibly illuminates"):return
		for other in range(rings.size()):
			if other==index:continue
			if not _require(energy>float((rings[other]["material"] as ShaderMaterial).get_shader_parameter("accent_strength")),"Rings do not illuminate sequentially inside-out"):return
	var jets := 0
	for material: ShaderMaterial in candidate.get("fountain_materials"):
		if material.get_meta("estate_water_role", "")=="jet":
			jets+=1
			if not _require(float(material.get_shader_parameter("accent_strength"))>0.0,"Each rhythmic jet must receive its pressure-linked night light"):return
	if not _require(jets==19,"The central main plume, ten flower arcs and eight outer plumes must be lit"):return
	lighting.apply_environment(1.0, false)
	candidate.call("sample",9.0,false)
	for strip: MeshInstance3D in strips:
		if not _require(is_zero_approx((strip.get_active_material(0) as BaseMaterial3D).emission_energy_multiplier), "Daytime retained spillway edge emission"): return
	for entry: Dictionary in landing:
		if not _require(is_zero_approx(float((entry.material as ShaderMaterial).get_shader_parameter("accent_strength"))), "Daytime retained landing-ring glow"): return
	for material: ShaderMaterial in candidate.get("spillway_materials"):
		if not _require(is_zero_approx(float(material.get_shader_parameter("accent_strength"))), "Daytime retained waterfall glow"): return
	if not _require(is_zero_approx(float(curtain_material.get_shader_parameter("waterfall_glow"))), "Daytime waterfall area effect must be off"): return
	for material: ShaderMaterial in candidate.get("fountain_materials"):
		if not _require(is_zero_approx(float(material.get_shader_parameter("accent_strength"))),"Daytime retained fountain emission"):return
	if not _require(candidate.find_children("*","MeshInstance3D",true,false).size() == 30 and source.find_children("*","MeshInstance3D",true,false).size()==original_meshes,"Retain the fountain and edge strips plus the submerged inlet sill without altering source meshes"):return
	print("PASS two joined spillway ribbons, full-sheet animated waterfall without point lamp, four landing rings; original fountain retained; daytime off; visual approval pending")
	source.free()
	candidate.free()
	# The explicit cropped review has no OutdoorLighting child. Its channel
	# guides must use the same source contour without requiring a composed world.
	var raw := load("res://rooms/estate/ElfieNest-complete-final.glb").instantiate() as Node3D
	root.add_child(raw)
	preload("res://rooms/estate/estate_daylight.gd").apply(raw)
	preload("res://rooms/estate/estate_water.gd").attach(raw)
	var raw_display := DISPLAY.new()
	root.add_child(raw_display)
	raw_display.bind(raw, Environment.new())
	raw_display.sample(4.0, true)
	if not _require(raw_display.find_children("SpillwayEdge*", "MeshInstance3D", true, false).size() == 2, "Raw water review must still bind both channel edges from the shared contour"): return
	raw_display.free()
	raw.free()
	print("PASS raw-water authoring review uses the same shoreline projection")
	quit(0)

func _require(ok: bool,message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok
