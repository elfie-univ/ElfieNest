extends RefCounted
## Offline V4 fixture geometry, derived from the actual estate ground and paths.
const GEOMETRY := preload("res://scripts/tools/outdoor_lighting_geometry.gd")
var result: Node3D
var high_poles: Array[Dictionary] = []
var forest_lamps: Array[Dictionary] = []

func build(source: Node3D) -> Node3D:
	result = Node3D.new()
	result.name = "OutdoorLighting"
	source.get_parent().add_child(result)
	var planting_boundaries: Array = []
	var ground: Array[MeshInstance3D] = []
	var trail: MeshInstance3D
	var road: MeshInstance3D
	for mesh: MeshInstance3D in source.find_children("*", "MeshInstance3D", true, false):
		var e: Dictionary = mesh.get_meta("extras", {})
		if e.get("landscape_ground_region", "") == "planting": planting_boundaries = e.landscape_ground_boundary_xz
		if e.get("landscape_ground_region", "") in ["ring", "plaza", "lawn", "planting", "woodland", "lakeside_paving"] or bool(e.get("forestTrail", false)): ground.append(mesh)
		if bool(e.get("forestTrail", false)): trail = mesh
		if str(mesh.name) == "ROAD REF • ring continuous warm-grey stone bed": road = mesh
	var plaza_pair := _symmetric_plaza_pair(source,road,trail)
	assert(is_finite(plaza_pair.x), "No clear mirrored outer-corner position for plaza lamps")
	_high("G1", Vector3(-plaza_pair.x,-0.06,plaza_pair.y),3.8,8.0,24.0)
	_high("P05", Vector3(plaza_pair.x,-0.06,plaza_pair.y),3.8,8.0,24.0)
	# W01 moves to the real authored woodland/lawn seam, away from open lawn.
	var lawn := source.find_child("CY SHORE solid Continuous lawn with true lake opening",true,false) as MeshInstance3D
	var nearest := Vector2(INF,INF)
	var best := INF
	for outline: Dictionary in (lawn.get_meta("extras") as Dictionary).landscape_ground_boundary_xz:
		for point: Array in outline.points:
			var candidate := Vector2(point[0],point[1])
			if candidate.x < -25.0 and candidate.y < 16.8 and candidate.distance_squared_to(Vector2(-33,16.8)) < best:
				best = candidate.distance_squared_to(Vector2(-33,16.8))
				nearest = candidate
	assert(is_finite(nearest.x), "Western woodland seam missing")
	_high("W01",Vector3(nearest.x,-0.06,nearest.y),4.0,2.2,28.0)
	var platform := source.find_child("CY R003 circular waterfront platform closed foundation",true,false) as MeshInstance3D
	var platform_bounds := platform.global_transform*platform.get_aabb()
	var back := Vector2(platform_bounds.get_center().x,platform_bounds.position.z-0.8)
	var planted: Vector2 = GEOMETRY.planting_edge(planting_boundaries, back)
	_high("H01",Vector3(planted.x,-0.06,planted.y),3.3,2.6,18.0)
	assert(trail != null and road != null, "Real road and forest route required")
	_forest(trail,road)
	_outer_ring(source,road,trail)
	if not preload("res://scripts/tools/outdoor_lighting_edges.gd").build(source,result,road): return null
	var lake := source.find_child("COMPLETE Inset natural lake",true,false) as MeshInstance3D
	var shore := GEOMETRY.contour(lake)
	var bank := source.find_child("CY R003 corrected CY R002 continuous natural shore slope 0",true,false) as MeshInstance3D
	var shore_height := (bank.global_transform*bank.get_aabb()).end.y+0.012
	for i in range(shore.size()): shore[i].y = shore_height
	var shoreline_polygon := PackedVector2Array()
	for i in range(shore.size()-1): shoreline_polygon.append(Vector2(shore[i].x,shore[i].z))
	var emitter := GEOMETRY.shoreline_rim(shoreline_polygon, shore_height)
	GEOMETRY.strip(result,emitter,0.08,"WholeLakeConcealedRim")
	result.set_meta("shoreline_emitter",emitter)
	var pool := source.find_child("Reference fountain water",true,false) as MeshInstance3D
	var pool_rim := GEOMETRY.contour(pool)
	var coping := source.find_child("ROAD REF • fountain radial limestone coping",true,false) as MeshInstance3D
	var pool_height := (coping.global_transform*coping.get_aabb()).end.y+0.008
	for i in range(pool_rim.size()): pool_rim[i].y = pool_height
	GEOMETRY.strip(result,pool_rim,0.10,"FountainConcealedRim")
	var patches: Array[String] = []
	for mesh in ground: patches.append_array(GEOMETRY.partition(mesh,result))
	result.set_meta("high_poles",high_poles)
	result.set_meta("forest_lamps",forest_lamps)
	result.set_meta("shoreline",shore)
	result.set_meta("fountain_rim",pool_rim)
	result.set_meta("ground_patches",patches)
	result.set_meta("source_model_sha256",FileAccess.get_sha256("res://rooms/estate/ElfieNest-complete-final.glb"))
	return result

func _symmetric_plaza_pair(source: Node3D, road: MeshInstance3D, trail: MeshInstance3D) -> Vector2:
	var surfaces: Array = [road,trail]
	for mesh: MeshInstance3D in source.find_children("*","MeshInstance3D",true,false):
		if str(mesh.get_meta("extras",{}).get("landscape_ground_region","")) in ["plaza","lakeside_paving"]:surfaces.append(mesh)
	var pavement := paving_triangles(surfaces)
	var chosen := Vector2(INF,INF)
	var best := INF
	# The outer pair may stand on lawn, but never occupies paving or a junction.
	for xi in range(160,201):
		for zi in range(160,201):
			var point := Vector2(xi*0.1,zi*0.1)
			if footprint_overlaps(Vector3(point.x,0,point.y),pavement,0.5) or footprint_overlaps(Vector3(-point.x,0,point.y),pavement,0.5):continue
			if point.distance_squared_to(Vector2(17,17))<best:
				best=point.distance_squared_to(Vector2(17,17));chosen=point
				if best==0.0:return chosen
	return chosen

func _outer_ring(source: Node3D, road: MeshInstance3D, trail: MeshInstance3D) -> void:
	var inner: Array[MeshInstance3D]=[]
	for mesh: MeshInstance3D in source.find_children("*","MeshInstance3D",true,false):
		var e: Dictionary=mesh.get_meta("extras",{})
		if str(e.get("outdoor_fixture_id","")).begins_with("R") and bool(e.get("lighting_diffuser",false)):inner.append(mesh)
	inner.sort_custom(func(a: MeshInstance3D,b: MeshInstance3D):return str(a.get_meta("extras").outdoor_fixture_id)<str(b.get_meta("extras").outdoor_fixture_id))
	var access := preload("res://rooms/estate/estate_outdoor_access.gd").new()
	access.load_precompiled(load("res://rooms/estate/estate_spatial.res"))
	var pavement := paving_triangles([road,trail])
	var ring := paving_triangles([road])
	for i in range(inner.size()-1):
		var a := Vector2(inner[i].global_position.x,inner[i].global_position.z).normalized()
		var b := Vector2(inner[i+1].global_position.x,inner[i+1].global_position.z).normalized()
		var direction := (a+b).normalized()
		var outer_radius := 0.0
		for step in range(150,250):
			var p := direction*step*0.1
			if footprint_overlaps(Vector3(p.x,0,p.y),ring,0.0):outer_radius=step*0.1
		if outer_radius==0:continue
		var point := direction*(outer_radius+0.7)
		var position := Vector3(point.x,-0.065,point.y)
		if footprint_overlaps(position,pavement,0.4) or access.contains_outdoor_point(point):continue
		var fixture := Node3D.new();fixture.name="Fixture_O%02d"%(i+1);result.add_child(fixture);fixture.position=position
		for part: String in ["housing","diffuser"]:
			var original := source.find_child("Outdoor R01 "+part,true,false) as MeshInstance3D
			assert(original!=null)
			var copy := original.duplicate() as MeshInstance3D
			fixture.add_child(copy);copy.transform=Transform3D.IDENTITY;copy.name=part.capitalize()
			var extras: Dictionary=copy.get_meta("extras",{}).duplicate(true)
			extras.outdoor_fixture_id="O%02d"%(i+1)
			for light: Dictionary in extras.get("design_lights",[]):
				light.merge({"intensity":PI,"distance":14.0,"angle":deg_to_rad(78.0),"attenuation":0.7,"angle_attenuation":0.2},true)
			copy.set_meta("extras",extras)

	access.free()

func _high(id: String, point: Vector3, height: float, energy: float, reach: float) -> void:
	_lamp(id,point,height,energy,reach,80.0,"high")
	high_poles.append({"id":id,"point":point,"height":height})

func _forest(trail: MeshInstance3D,road: MeshInstance3D) -> void:
	var pavement := paving_triangles([road,trail])
	var planned: Array[Vector3] = []
	var e: Dictionary = trail.get_meta("extras")
	var half_width := float(e.forest_trail_width_m)*0.5
	for raw: Array in e.forest_trail_paths:
		for sample: Dictionary in GEOMETRY.sample_path(raw,6.0):
			var direction: Vector3 = sample.direction
			var normal := Vector3(-direction.z,0,direction.x).normalized()
			var offset := half_width+0.4
			var point: Vector3 = sample.point+normal*offset-Vector3.UP*0.05
			var close := false
			for existing: Vector3 in planned:
				if point.distance_to(existing) < 2.5: close = true
			if close: continue
			planned.append(point)
			# Preserve original candidate IDs/spacing when removing a junction lamp.
			if footprint_overlaps(point,pavement):continue
			_lamp("L%02d"%planned.size(),point,0.6,1.15,8.5,83.0,"forest")
			forest_lamps.append({"point":point,"path_point":sample.point,"offset":offset,"half_width":half_width})

func _lamp(id: String, position: Vector3, height: float, energy: float, reach: float, angle: float, group: String) -> void:
	var parent := Node3D.new()
	parent.name = "Fixture_"+id
	result.add_child(parent)
	parent.position = position
	var metal := StandardMaterial3D.new()
	metal.albedo_color = Color(0.12,0.13,0.12)
	metal.roughness = 0.8
	var lens := StandardMaterial3D.new()
	lens.resource_name = "Outdoor warm shielded lamp diffuser"
	lens.albedo_color = Color(0.72,0.65,0.46)
	lens.emission_enabled = true
	lens.emission = Color(1.0,0.79,0.5)
	lens.emission_energy_multiplier = 0.7
	var parts: Array=[["Housing",height,0.07,height*0.5],["Shield",0.07,0.15,height],["Diffuser",0.025,0.10,height-0.045]]
	if height>2.0:
		parts=[["Housing",height-0.16,0.065,(height-0.16)*0.5],["Shield",0.12,0.40,height],["Diffuser",0.14,0.42,height-0.10]]
	for item: Array in parts:
		var cylinder := CylinderMesh.new()
		cylinder.height = maxf(float(item[1]),0.008)
		cylinder.top_radius = item[2]
		cylinder.bottom_radius = item[2]
		cylinder.radial_segments = 48 if height>2.0 else 12
		if height>2.0 and item[0]=="Shield":cylinder.top_radius=0.33
		var diffuse: bool = item[0] == "Diffuser"
		cylinder.material = lens if diffuse else metal
		var mesh := MeshInstance3D.new()
		mesh.name = str(item[0])
		mesh.mesh = cylinder
		mesh.position.y = item[3]
		var e := {"outdoor_fixture_id":id,"outdoor_fixture_group":group,"lighting_diffuser":diffuse,"full_height":true,"furniture":false}
		if diffuse:
			e["design_lights"] = [{"type":"spot","position":[0,-0.10 if height>2.0 else -0.03,0],"target":[0,-1,0],"color":0xffdfb5,"intensity":energy*PI,"distance":reach,"angle":deg_to_rad(angle),"attenuation":0.7,"angle_attenuation":0.2}]
		if diffuse and id in ["G1","P05"]:
			# Aim the broad pool into the plaza, rather than straight onto the planting.
			e.design_lights[0].target = [-signf(position.x)*5.0,-3.6,5.0]
			e.design_lights[0].angle = deg_to_rad(65.0)
		mesh.set_meta("extras",e)
		parent.add_child(mesh)

static func paving_triangles(meshes: Array) -> Array[PackedVector2Array]:
	var result: Array[PackedVector2Array] = []
	for mesh: MeshInstance3D in meshes:
		var faces := mesh.mesh.get_faces()
		for i in range(0,faces.size(),3):
			var a: Vector3=mesh.global_transform*faces[i]
			var b: Vector3=mesh.global_transform*faces[i+1]
			var c: Vector3=mesh.global_transform*faces[i+2]
			if (b-a).cross(c-a).y<=0.0000001:continue
			result.append(PackedVector2Array([Vector2(a.x,a.z),Vector2(b.x,b.z),Vector2(c.x,c.z)]))
	return result

static func footprint_overlaps(point: Vector3,triangles: Array[PackedVector2Array],radius: float=0.25) -> bool:
	var p := Vector2(point.x,point.z)
	for triangle: PackedVector2Array in triangles:
		if Geometry2D.is_point_in_polygon(p,triangle):return true
		for i in range(3):
			var a := triangle[i]
			var edge := triangle[(i+1)%3]-a
			var t := clampf((p-a).dot(edge)/maxf(edge.length_squared(),0.000000001),0.0,1.0)
			if p.distance_squared_to(a+edge*t)<radius*radius:return true
	return false
