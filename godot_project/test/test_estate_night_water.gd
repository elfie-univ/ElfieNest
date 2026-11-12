extends SceneTree
## The original fountain water glows; rings illuminate strictly inside-out.
const DISPLAY := preload("res://nest/estate/estate_water_display.gd")
const LIGHTING := preload("res://nest/estate/estate_lighting_sample.gd")
func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var source := load("res://nest/assembly/estate.tscn").instantiate() as Node3D
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
		var route: PackedVector3Array = strip.get_meta("light_route")
		if not _require(route.size() >= 2 and points.size() == route.size() * 2 + 12, "Retain upper-edge pairs plus the existing twelve-vertex rounded nose"): return
		var first_across := Vector3.ZERO
		for vertex: int in range(0, route.size() * 2, 2):
			# The final twelve vertices form a rounded cap, not additional width pairs.
			var a := strip.global_transform * points[vertex]
			var b := strip.global_transform * points[vertex + 1]
			var across := b - a
			var width := absf(across.z)
			# Each stored float32 endpoint can round by one ULP at its world scale.
			# Four ULPs bound two endpoints and the world-transform arithmetic.
			var tolerance := 4.0 * pow(2.0, -23.0) * maxf(1.0, maxf(absf(a.z), absf(b.z)))
			print("SPILLWAY_WIDTH strip=", strip.name, " pair=", vertex / 2, " world_width=", width, " design=0.1 tolerance=", tolerance)
			if not _require(absf(width - 0.10) <= tolerance, "World channel width differs from 10 cm beyond float32 endpoint precision: width=%0.9f tolerance=%0.9f" % [width, tolerance]): return
			if vertex == 0: first_across = across
			elif not _require(across.dot(first_across) > 0.009, "Channel guide twists at the waterfall corner"): return
		var rim := source.find_child("FountainConcealedRim", true, false) as MeshInstance3D
		var rim_material := rim.get_active_material(0) as BaseMaterial3D
		var edge_material := strip.get_active_material(0) as BaseMaterial3D
		if not _require(edge_material.emission == rim_material.emission and edge_material.albedo_color == rim_material.albedo_color and is_equal_approx(edge_material.emission_energy_multiplier, rim_material.emission_energy_multiplier), "Channel guides must match the fountain rim color and night brightness"): return
		if not _require(absf(route[0].y-route[-1].y) < 0.1, "Channel lamps must follow the gently graded upper edge"): return
		var coping := source.find_child("ROAD REF • fountain radial limestone coping", true, false) as MeshInstance3D
		if not _require(absf(route[0].y - (coping.global_transform * coping.get_aabb()).end.y - 0.008) < 0.002, "The channel must touch the fountain rim at its real elevation"): return
		var curtain_edge := source.find_child("Continuous shallow waterfall from solid spillway crest", true, false) as MeshInstance3D
		var end_x := (curtain_edge.global_transform * curtain_edge.get_aabb()).position.x
		var side := str(strip.name).trim_prefix("SpillwayEdge_")
		var wall := source.find_child("CY R001 spillway %s continuous side wall" % side, true, false) as MeshInstance3D
		if not _require(wall != null and _check_nose_on_stone(strip, wall, end_x, route.size()*2), "Rounded channel nose must reach the crest while remaining on actual stone"): return
		var coping_faces := coping.mesh.get_faces()
		for point: Vector3 in route:
			for face in range(0, coping_faces.size(), 3):
				var hit: Variant = Geometry3D.segment_intersects_triangle(Vector3(point.x, 2.0, point.z), Vector3(point.x, -1.0, point.z), coping.global_transform * coping_faces[face], coping.global_transform * coping_faces[face + 1], coping.global_transform * coping_faces[face + 2])
				if hit is Vector3 and not _require(point.y >= hit.y + 0.004, "The inlet guide must remain above the real coping rather than disappear inside its stone"): return

		if not _require((strip.get_active_material(0) as BaseMaterial3D).emission_energy_multiplier > 0.0, "Spillway edge light is dark at night"): return
	if not _require(not preload("res://nest/estate/estate_opaque.gdshader").code.contains("spillway_return"), "Remove the rejected soil-patch glow rather than hide it beneath the ribbon"): return
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
	if not _require(lake_material.get_shader_parameter("night_reflection") == 1.0, "Night lake must receive its sky independently of extinguished room ambient light"): return
	candidate.set_night(false)
	if not _require(lake_material.get_shader_parameter("night_reflection") == 0.0, "Night sky reflection must not alter daytime water"): return
	candidate.set_sky_night(true)
	candidate.set("_on_screen", true)
	candidate._process(0.1)
	if not _require(lake_material.get_shader_parameter("night_reflection") == 1.0 and lake_material.get_shader_parameter("accent_strength") == 0.0, "Quiet night must retain sky reflections with show lighting off"): return
	candidate.sample(0.55, true)
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
	var show: Node3D = candidate.fountain_show
	if not _require(show.jets.size() == 9 and show.central_jets.size() == 8, "Retain nine real nozzles and eight animated flower arcs"): return
	for time: float in [8.0, 46.0]:
		candidate.sample(time, true)
		var active := 0
		for jet: MeshInstance3D in show.jets:
			var material := jet.get_active_material(0) as ShaderMaterial
			if float(material.get_shader_parameter("jet_height")) <= 0.01: continue
			active += 1
			if not _require(float(material.get_shader_parameter("accent_strength")) > 0.0, "Active nocturnal plume lost its pressure-linked illumination"): return
		for flower: Dictionary in show.central_jets:
			var material := flower.material as ShaderMaterial
			if float(material.get_shader_parameter("jet_height")) <= 0.01: continue
			active += 1
			if not _require(float(material.get_shader_parameter("accent_strength")) > 0.0, "Active nocturnal flower arc lost its illumination"): return
		if not _require(active > 0, "Night programme has no active plume or flower arc"): return
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
	if not _require(source.find_children("*","MeshInstance3D",true,false).size()==original_meshes,"Retain the fountain and edge strips plus the submerged inlet sill without altering source meshes"):return
	print("PASS two joined spillway ribbons, full-sheet animated waterfall without point lamp, four landing rings; original fountain retained; daytime off; visual approval pending")
	candidate.free()
	source.free()
	# Bind a fresh split review independently; both channel guides must resolve
	# from current source geometry without the retired lighting layout.
	var raw := load("res://nest/assembly/estate.tscn").instantiate() as Node3D
	root.add_child(raw)
	preload("res://nest/estate/estate_water.gd").attach(raw)
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

func _check_nose_on_stone(strip: MeshInstance3D, wall: MeshInstance3D, crest_x: float, cap_start: int) -> bool:
	var points: PackedVector3Array = strip.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var wall_faces := wall.mesh.get_faces()
	for index: int in wall_faces.size(): wall_faces[index] = wall.global_transform * wall_faces[index]
	var maximum_x := -INF
	var minimum_clearance := INF
	var maximum_clearance := -INF
	var center := strip.global_transform * points[cap_start]
	# Include the last body pair, cap centre and arc vertices, not the inlet miter.
	for index: int in range(cap_start-2, points.size()):
		var point := strip.global_transform * points[index]
		maximum_x = maxf(maximum_x, point.x)
		var top := -INF
		for face: int in range(0, wall_faces.size(), 3):
			var hit: Variant = Geometry3D.segment_intersects_triangle(point+Vector3.UP*2.0, point-Vector3.UP*2.0, wall_faces[face], wall_faces[face+1], wall_faces[face+2])
			if hit is Vector3: top = maxf(top, (hit as Vector3).y)
		# The lamp is a flat full-width ribbon over a rounded stone crown.
		# Its side edges may overhang the curved cross-section; support is
		# measured on the real crown, with the whole footprint inside the wall.
		var footprint := wall.global_transform * wall.get_aabb()
		if not _require(point.x >= footprint.position.x-0.001 and point.x <= footprint.end.x+0.001 and point.z >= footprint.position.z-0.001 and point.z <= footprint.end.z+0.001, "Flat lamp nose extends outside its supporting wall footprint"): return false
		if is_finite(top):
			var clearance := point.y-top
			minimum_clearance = minf(minimum_clearance, clearance)
			maximum_clearance = maxf(maximum_clearance, clearance)
			if not _require(clearance >= 0.014-0.001, "Flat lamp strip intersects its rounded supporting stone"): return false
		var crown_top := -INF
		var crown := Vector3(point.x, point.y, center.z)
		for face: int in range(0, wall_faces.size(), 3):
			var hit: Variant = Geometry3D.segment_intersects_triangle(crown+Vector3.UP*2.0, crown-Vector3.UP*2.0, wall_faces[face], wall_faces[face+1], wall_faces[face+2])
			if hit is Vector3: crown_top = maxf(crown_top, hit.y)
		if not _require(is_finite(crown_top) and absf(point.y-crown_top-0.014) <= 0.001, "Flat lamp nose must remain 14 mm above the actual stone crown"): return false
	var bounds := wall.global_transform * wall.get_aabb()
	var last_pair_center := strip.global_transform * ((points[cap_start-2]+points[cap_start-1])*0.5)
	var rounding := 4.0*pow(2.0,-23.0)*maxf(1.0,absf(maximum_x))
	print("SPILLWAY_NOSE strip=", strip.name, " crest_x=", crest_x, " body_end=", last_pair_center, " tip_x=", maximum_x, " stone_end_x=", bounds.end.x, " stone_margin=", bounds.end.x-maximum_x, " clearance_min=", minimum_clearance, " clearance_max=", maximum_clearance)
	return _require(center.distance_to(last_pair_center) <= rounding and maximum_x > crest_x and maximum_x > center.x and maximum_x <= bounds.end.x-0.001+rounding, "Actual rounded nose must continue past the crest and stop within the supporting stone")
