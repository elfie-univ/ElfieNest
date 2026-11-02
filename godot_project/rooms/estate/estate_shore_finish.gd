extends RefCounted
## Follow the real bank geometry; keep land foliage clear of the water edge.

var water := PackedVector2Array()
var water_bounds := Rect2()
var water_height := 0.0
var bench_clearance:=AABB()
var estate_frame:=Transform3D.IDENTITY
var _plant_bounds: Dictionary={}

func apply(estate: Node3D, layout: Node3D) -> void:
	var old_rim := layout.find_child("WholeLakeConcealedRim", true, false) as MeshInstance3D
	if old_rim != null: old_rim.hide()
	var outline: PackedVector3Array = layout.get_meta("shoreline")
	for i in range(outline.size() - 1): water.append(Vector2(outline[i].x, outline[i].z))
	water_bounds = Rect2(water[0], Vector2.ZERO)
	for point: Vector2 in water: water_bounds = water_bounds.expand(point)
	var lake := estate.find_child("COMPLETE Inset natural lake", true, false) as MeshInstance3D
	water_height = (lake.global_transform * lake.get_aabb()).end.y
	estate_frame=estate.global_transform
	var first:=true
	for part: MeshInstance3D in estate.find_children("Lakeside*","MeshInstance3D",true,false):
		if not ("bench" in str(part.name) or str(part.name).begins_with("Lakeside back frame")):continue
		var box:=part.global_transform*part.get_aabb()
		bench_clearance=box if first else bench_clearance.merge(box)
		first=false
	bench_clearance=bench_clearance.grow(0.35)
	bench_clearance.position.y=0.65
	bench_clearance.size.y=2.0
	estate.set_meta("bank_triangles_clipped",preload("res://rooms/estate/estate_bank_cleanup.gd").apply(estate,water,water_bounds,water_height))
	var path := ribbon_path(estate)
	var top := path[0].y
	var contour := PackedVector2Array()
	for i in range(path.size()): contour.append(Vector2(path[i].x, path[i].z))
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var uv := PackedVector2Array()
	var indices := PackedInt32Array()
	for i in range(contour.size()):
		var point := contour[i]
		var tangent := (contour[mini(i + 1, contour.size() - 1)] - contour[maxi(i - 1, 0)]).normalized()
		var inward := Vector2(-tangent.y, tangent.x)
		if not Geometry2D.is_point_in_polygon(point + inward * 0.02, contour): inward = -inward
		# The same softly rounded, full-height cross-section runs around the
		# entire shore. Shared indexed vertices leave no independent end caps.
		for profile: Vector2 in [Vector2(-0.035, top - 0.02), Vector2(0.0, top), Vector2(0.04, top - 0.035), Vector2(0.085, water_height + 0.002)]:
			var xz := point + inward * profile.x
			vertices.append(Vector3(xz.x, profile.y, xz.y))
			normals.append(Vector3(inward.x, 0.2, inward.y).normalized())
			uv.append(Vector2(0.5, clampf((profile.y - water_height) / (top - water_height), 0.0, 1.0)))
	for i in range(contour.size() - 1):
		var next := i + 1
		for row in range(3):
			var a := i * 4 + row
			var b := next * 4 + row
			indices.append_array(PackedInt32Array([a, b, b + 1, a, b + 1, a + 1]))
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TEX_UV] = uv
	arrays[Mesh.ARRAY_INDEX] = indices
	var ribbon_mesh := ArrayMesh.new()
	ribbon_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var image := Image.create(1, 64, false, Image.FORMAT_RGB8)
	for y in range(64):
		var strength := pow(float(y) / 63.0, 1.5)
		image.set_pixel(0, y, Color(strength, strength, strength).linear_to_srgb())
	var material := StandardMaterial3D.new()
	material.resource_name = "Outdoor shoreline concealed warm wash lamp"
	material.albedo_color = Color(0.68, 0.57, 0.38)
	material.roughness = 0.8
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.emission_enabled = true
	material.emission = Color(1.0, 0.77, 0.44)
	material.emission_energy_multiplier = 1.1
	material.emission_operator = BaseMaterial3D.EMISSION_OP_MULTIPLY
	material.emission_texture = ImageTexture.create_from_image(image)
	ribbon_mesh.surface_set_material(0, material)
	var ribbon := MeshInstance3D.new()
	ribbon.name = "WholeLakeRibbon"
	ribbon.mesh = ribbon_mesh
	ribbon.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	ribbon.set_meta("extras", {"outdoor_fixture_id": "shoreline-wash", "lighting_diffuser": true})
	ribbon.set_meta("shoreline", path)
	layout.add_child(ribbon)
	ribbon.global_transform = Transform3D.IDENTITY

static func ribbon_path(estate: Node3D) -> PackedVector3Array:
	# The composed world and the cropped water review use the same source
	# boundary and the same contour operation, without local connector patches.
	var lake := estate.find_child("COMPLETE Inset natural lake", true, false) as MeshInstance3D
	var reader := preload("res://rooms/estate/estate_outdoor_access.gd").new()
	var loops: Array[PackedVector2Array] = reader._top_outlines(lake, 0, -1.0)
	reader.free()
	var water_outline := PackedVector2Array()
	var largest := 0.0
	for loop: PackedVector2Array in loops:
		var area := 0.0
		for i in range(loop.size()): area += loop[i].cross(loop[(i + 1) % loop.size()])
		if absf(area) > largest:
			largest = absf(area)
			water_outline = loop
	assert(not water_outline.is_empty(), "The real lake must have a closed boundary")
	# A uniform opening removes narrow folded tips in the authored outline;
	# it does not add an independent cap at the platform junction.
	var inset := Geometry2D.offset_polygon(water_outline, -0.35, Geometry2D.JOIN_ROUND)
	assert(inset.size() == 1, "The lake ribbon must remain one closed contour")
	var opened := Geometry2D.offset_polygon(inset[0], 0.315, Geometry2D.JOIN_ROUND)
	assert(opened.size() == 1, "The lake ribbon must remain one closed contour")
	var contour := PackedVector2Array()
	for point: Vector2 in opened[0]:
		if contour.is_empty() or contour[-1].distance_to(point) > 0.06: contour.append(point)
	for pass_index in range(2):
		var rounded := PackedVector2Array()
		for i in range(contour.size()):
			var a := contour[i]
			var b := contour[(i + 1) % contour.size()]
			rounded.append(a.lerp(b, 0.25))
			rounded.append(a.lerp(b, 0.75))
		contour = rounded
	var bank := estate.find_child("CY R003 corrected CY R002 continuous natural shore slope 0", true, false) as MeshInstance3D
	var platform := estate.find_child("CY R003 circular waterfront platform closed foundation", true, false) as MeshInstance3D
	var top := maxf((bank.global_transform * bank.get_aabb()).end.y, (platform.global_transform * platform.get_aabb()).end.y) + 0.012
	var north := estate.find_child("CY R001 spillway north continuous side wall", true, false) as MeshInstance3D
	var south := estate.find_child("CY R001 spillway south continuous side wall", true, false) as MeshInstance3D
	var north_box := north.global_transform * north.get_aabb()
	var south_box := south.global_transform * south.get_aabb()
	var curtain := estate.find_child("Continuous shallow waterfall from solid spillway crest", true, false) as MeshInstance3D
	var fall := curtain.global_transform * curtain.get_aabb()
	var opening := Rect2(Vector2(fall.position.x - 0.4, north_box.end.z - 0.05), Vector2(fall.size.x + 0.8, south_box.position.z + 0.05 - (north_box.end.z - 0.05)))
	# Split at the real channel sides before opening the loop. Both guides
	# then terminate on these exact crest vertices, leaving the water clear.
	var split := PackedVector3Array()
	for i in range(contour.size()):
		var a := contour[i]
		var b := contour[(i + 1) % contour.size()]
		var cuts: Array[float] = [0.0]
		if absf(b.y - a.y) > 0.00001:
			for z: float in [opening.position.y, opening.end.y]:
				var t := (z - a.y) / (b.y - a.y)
				var point := a.lerp(b, t)
				if t > 0.00001 and t < 0.99999 and point.x > opening.position.x and point.x < opening.end.x: cuts.append(t)
		cuts.sort()
		for t: float in cuts:
			var point := a.lerp(b, t)
			split.append(Vector3(point.x, top, point.y))
	var clear: Array[bool] = []
	for i in range(split.size()):
		var midpoint := (split[i] + split[(i + 1) % split.size()]) * 0.5
		clear.append(not opening.has_point(Vector2(midpoint.x, midpoint.z)))
	var start := -1
	for i in range(split.size()):
		if clear[i] and not clear[posmod(i - 1, split.size())]:
			assert(start == -1, "Only the real waterfall may interrupt the shore ribbon")
			start = i
	assert(start >= 0, "The shoreline must meet both sides of the real waterfall")
	var path := PackedVector3Array([split[start]])
	for step in range(split.size()):
		var index := (start + step) % split.size()
		if not clear[index]: break
		path.append(split[(index + 1) % split.size()])
	return path

func nearest_edge(point: Vector2) -> Vector2:
	var nearest := water[0]
	var best := INF
	for i in range(water.size()):
		var candidate := Geometry2D.get_closest_point_to_segment(point, water[i], water[(i + 1) % water.size()])
		var distance := candidate.distance_squared_to(point)
		if distance < best:
			best = distance
			nearest = candidate
	return nearest

func retreat_plants(mesh: Mesh, buffer: PackedFloat32Array) -> int:
	var selected := false
	for surface in range(mesh.get_surface_count()):
		var material := mesh.surface_get_material(surface)
		if material != null and str(material.resource_name).begins_with("Layered low groundcover"): selected = true
	if not selected: return 0
	var moved := 0
	var bounds := mesh.get_aabb()
	for index in range(buffer.size() / 12):
		var offset := index * 12
		var root := Vector2(buffer[offset + 3], buffer[offset + 11])
		if not water_bounds.grow(2.0).has_point(root): continue
		var radius := 0.0
		for corner in range(8):
			var local := bounds.get_endpoint(corner)
			var delta := Vector2(buffer[offset] * local.x + buffer[offset + 1] * local.y + buffer[offset + 2] * local.z, buffer[offset + 8] * local.x + buffer[offset + 9] * local.y + buffer[offset + 10] * local.z)
			radius = maxf(radius, delta.length())
		var destination := root
		for attempt in range(6):
			var nearest := nearest_edge(destination)
			var inside := Geometry2D.is_point_in_polygon(destination, water)
			if not inside and destination.distance_to(nearest) >= radius + 0.55: break
			var outward := (destination - nearest).normalized()
			if inside: outward = -outward
			if outward.is_zero_approx(): outward = (nearest - water_bounds.get_center()).normalized()
			destination = nearest + outward * (radius + 0.56)
		if destination.distance_to(root) < 0.001: continue
		buffer[offset + 3] = destination.x
		buffer[offset + 11] = destination.y
		moved += 1
	return moved

func filter_plant_instances(mesh: Mesh, buffer: PackedFloat32Array) -> Dictionary:
	var identity:=mesh.get_instance_id()
	if not _plant_bounds.has(identity):
		var actual:=AABB()
		var first:=true
		var plant:=false
		for s in range(mesh.get_surface_count()):
			var material:=mesh.surface_get_material(s) as BaseMaterial3D
			if material!=null and material.shading_mode==BaseMaterial3D.SHADING_MODE_PER_PIXEL and material.transparency==BaseMaterial3D.TRANSPARENCY_DISABLED and not material.emission_enabled:plant=true
			var points: PackedVector3Array=mesh.surface_get_arrays(s)[Mesh.ARRAY_VERTEX]
			for point in points:
				actual=AABB(point,Vector3.ZERO) if first else actual.expand(point)
				first=false
		_plant_bounds[identity]={"bounds":actual,"plant":plant and actual.size.y<3.0 and actual.size.x<4.0 and actual.size.z<4.0}
	var definition: Dictionary=_plant_bounds[identity]
	var kept:=PackedFloat32Array()
	var indices:=PackedInt32Array()
	var removed:=PackedInt32Array()
	var bench:=0;var lake:=0
	for i in range(buffer.size()/12):
		var o:=i*12
		var pose:=Transform3D(Basis(Vector3(buffer[o],buffer[o+4],buffer[o+8]),Vector3(buffer[o+1],buffer[o+5],buffer[o+9]),Vector3(buffer[o+2],buffer[o+6],buffer[o+10])),Vector3(buffer[o+3],buffer[o+7],buffer[o+11]))
		var box: AABB=(estate_frame*pose)*(definition.bounds as AABB)
		var obstructs: bool=definition.plant and bench_clearance.intersects(box)
		var over_water:=false
		if definition.plant and box.position.y<water_height+0.3 and box.end.y<water_height+1.3:
			for corner in range(8):
				var point:=box.get_endpoint(corner)
				var xz:=Vector2(point.x,point.z)
				if water_bounds.has_point(xz) and Geometry2D.is_point_in_polygon(xz,water):over_water=true;break
		if obstructs or over_water:
			removed.append(i)
			if obstructs:bench+=1
			else:lake+=1
			continue
		indices.append(i);kept.append_array(buffer.slice(o,o+12))
	return {"buffer":kept,"indices":indices,"removed":removed,"bench":bench,"water":lake}
