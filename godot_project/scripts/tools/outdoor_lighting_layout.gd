extends RefCounted
## Offline V4 fixture geometry, derived from the actual estate ground and paths.
const GEOMETRY := preload("res://scripts/tools/outdoor_lighting_geometry.gd")
var result: Node3D
var high_poles: Array[Dictionary] = []
var forest_lamps: Array[Dictionary] = []
var plaza_light_focus := Vector3.ZERO

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
	var plaza := source.find_child(preload("res://scripts/tools/outdoor_lighting_edges.gd").PLAZA,true,false) as MeshInstance3D
	var faces := plaza.mesh.get_faces()
	var area := 0.0
	# Derive the shared aiming point from the actual paved surface.
	for i in range(0,faces.size(),3):
		var a := plaza.global_transform*faces[i]
		var b := plaza.global_transform*faces[i+1]
		var c := plaza.global_transform*faces[i+2]
		var weight := (b-a).cross(c-a).y
		if weight<=0.000001:continue
		plaza_light_focus+=(a+b+c)/3.0*weight
		area+=weight
	assert(area>0.0,"Plaza lights require a real paved surface")
	plaza_light_focus/=area
	result.set_meta("plaza_light_focus",plaza_light_focus)
	assert(is_finite(plaza_pair.x), "No clear mirrored plaza-edge position for lamps")
	_high("G1", Vector3(-plaza_pair.x,-0.06,plaza_pair.y),6.5,8.0,24.0)
	_high("P05", Vector3(plaza_pair.x,-0.06,plaza_pair.y),6.5,8.0,24.0)
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
	# Aim at the circular end, independent of the movable bench.
	var focus := Vector3(platform_bounds.end.x-4.8,0.095,platform_bounds.end.z-4.8)
	var position := _lakeside_lamp_position(source,Vector3(focus.x-1.6,-0.06,focus.z-5.0))
	_plaza_single_arm("H01",position,6.5,8.0,18.0,focus)
	high_poles.append({"id":"H01","point":position,"height":6.5})
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
	# Append new path fixtures after ground partitioning to preserve patch IDs.
	_ring_fixture(source,"B01",Vector3(24.0,-0.06,-3.15),85.0)
	_ring_fixture(source,"B02",Vector3(29.0,-0.06,-3.05),85.0)
	result.set_meta("high_poles",high_poles)
	result.set_meta("forest_lamps",forest_lamps)
	result.set_meta("shoreline",shore)
	result.set_meta("fountain_rim",pool_rim)
	result.set_meta("ground_patches",patches)
	result.set_meta("source_model_sha256",FileAccess.get_sha256("res://rooms/estate/ElfieNest-complete-final.glb"))
	return result

func _lakeside_lamp_position(source: Node3D, desired: Vector3) -> Vector3:
	var surfaces: Array=[]
	for mesh: MeshInstance3D in source.find_children("*","MeshInstance3D",true,false):
		var extras: Dictionary=mesh.get_meta("extras",{})
		if str(extras.get("landscape_ground_region","")) in ["ring","plaza","lakeside_paving"] or bool(extras.get("forestTrail",false)):
			surfaces.append(mesh)
	var nearby: Array[PackedVector2Array]=[]
	var search:=Rect2(Vector2(desired.x-1.5,desired.z-1.5),Vector2(3.0,3.0))
	for triangle: PackedVector2Array in paving_triangles(surfaces):
		var bounds:=Rect2(triangle[0],Vector2.ZERO).expand(triangle[1]).expand(triangle[2])
		if search.intersects(bounds,true):nearby.append(triangle)
	var candidates: Array[Vector3]=[]
	for x in range(-10,11):
		for z in range(-10,11):candidates.append(desired+Vector3(x*0.1,0,z*0.1))
	candidates.sort_custom(func(a: Vector3,b: Vector3):return a.distance_squared_to(desired)<b.distance_squared_to(desired))
	for point: Vector3 in candidates:
		if not footprint_overlaps(point,nearby,0.3):return point
	assert(false,"The marked left-hand lamp area needs a clear unpaved base")
	return desired

func _symmetric_plaza_pair(source: Node3D, road: MeshInstance3D, trail: MeshInstance3D) -> Vector2:
	var surfaces: Array = [road,trail]
	for mesh: MeshInstance3D in source.find_children("*","MeshInstance3D",true,false):
		if str(mesh.get_meta("extras",{}).get("landscape_ground_region","")) in ["plaza","lakeside_paving"]:surfaces.append(mesh)
	var pavement := paving_triangles(surfaces)
	var chosen := Vector2(INF,INF)
	var best := INF
	# Bring both poles to the plaza shoulders, leaving the paved junction clear.
	for xi in range(130,161):
		for zi in range(175,216):
			var point := Vector2(xi*0.1,zi*0.1)
			if footprint_overlaps(Vector3(point.x,0,point.y),pavement,0.35) or footprint_overlaps(Vector3(-point.x,0,point.y),pavement,0.35):continue
			if point.distance_squared_to(Vector2(14.8,18.8))<best:
				best=point.distance_squared_to(Vector2(14.8,18.8));chosen=point
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

func _ring_fixture(source: Node3D, id: String, point: Vector3, angle: float=78.0) -> void:
	var fixture:=Node3D.new()
	fixture.name="Fixture_"+id
	result.add_child(fixture)
	fixture.position=point
	for part: String in ["housing","diffuser"]:
		var original:=source.find_child("Outdoor R01 "+part,true,false) as MeshInstance3D
		assert(original!=null)
		var copy:=original.duplicate() as MeshInstance3D
		fixture.add_child(copy)
		copy.transform=Transform3D.IDENTITY
		copy.name=part.capitalize()
		var extras: Dictionary=copy.get_meta("extras",{}).duplicate(true)
		extras.outdoor_fixture_id=id
		extras.outdoor_fixture_group="path"
		for light: Dictionary in extras.get("design_lights",[]):
			# Emit from the path-facing diffuser surface, above the opaque lower
			# collar. The original central emitter is trapped inside that collar.
			light.merge({"position":[0.0,1.06,0.165],"target":[0.0,0.0,2.7],"intensity":PI,"distance":14.0,"angle":deg_to_rad(angle),"attenuation":0.7,"angle_attenuation":0.2},true)
		copy.set_meta("extras",extras)

func _high(id: String, point: Vector3, height: float, energy: float, reach: float) -> void:
	if id in ["G1","P05"]:
		_plaza_single_arm(id,point,height,energy,maxf(reach,34.0),plaza_light_focus)
	else:
		_lamp(id,point,height,energy,reach,80.0,"high")
	high_poles.append({"id":id,"point":point,"height":height})

func _plaza_single_arm(id: String, point: Vector3, height: float, energy: float, reach: float, focus: Vector3, size: float=1.0) -> void:
	var fixture := Node3D.new()
	fixture.name = "Fixture_"+id
	result.add_child(fixture)
	fixture.position = point
	var forward := Vector3(focus.x-point.x,0,focus.z-point.z).normalized()
	var across := Vector3(-forward.z,0,forward.x)
	var metal := StandardMaterial3D.new()
	metal.albedo_color = Color(0.16,0.18,0.14)
	metal.metallic = 0.35
	metal.roughness = 0.6
	var lens := StandardMaterial3D.new()
	lens.resource_name = "Outdoor warm single-arm lamp diffuser"
	lens.albedo_color = Color(0.72,0.65,0.46)
	lens.emission_enabled = true
	lens.emission = Color(1.0,0.79,0.5)
	lens.emission_energy_multiplier = 0.7
	# Sweep one rounded rectangular housing: upright shaft, smooth elbow,
	# then a slim rising arm, matching the single-sided reference streetlight.
	var turn := deg_to_rad(65.0)
	var radius := 0.60
	var elbow_y := height/size-radius*sin(turn)-1.70*cos(turn)-0.08
	var arm_start := forward*(radius*(1.0-cos(turn)))+Vector3.UP*(elbow_y+radius*sin(turn))
	var along := forward*sin(turn)+Vector3.UP*cos(turn)
	var underside := forward*cos(turn)-Vector3.UP*sin(turn)
	var stations: Array[Dictionary] = []
	for i in range(13):
		var t := float(i)/12.0
		stations.append({"centre":Vector3.UP*elbow_y*t,"out":forward,"width":lerpf(0.19,0.12,t),"depth":lerpf(0.16,0.085,t)})
	for i in range(1,17):
		var t := float(i)/16.0
		var angle := turn*t
		stations.append({"centre":forward*(radius*(1.0-cos(angle)))+Vector3.UP*(elbow_y+radius*sin(angle)),"out":forward*cos(angle)-Vector3.UP*sin(angle),"width":lerpf(0.12,0.25,t),"depth":lerpf(0.085,0.09,t)})
	for i in range(1,17):
		var t := float(i)/16.0
		stations.append({"centre":arm_start+along*(1.70*t),"out":underside,"width":0.25-0.02*pow(t,8.0),"depth":0.09-0.01*pow(t,8.0)})
	var rings: Array[PackedVector3Array] = []
	for station: Dictionary in stations:
		station.centre*=size
		station.width*=size
		station.depth*=size
		var ring := PackedVector3Array()
		for j in range(33):
			var angle := TAU*float(j)/32.0
			var u := signf(cos(angle))*pow(absf(cos(angle)),0.35)
			var v := signf(sin(angle))*pow(absf(sin(angle)),0.35)
			ring.append(station.centre+across*(station.width*u)+station.out*(station.depth*v))
		rings.append(ring)
	var shell := SurfaceTool.new()
	shell.begin(Mesh.PRIMITIVE_TRIANGLES)
	for i in range(rings.size()-1):
		for j in range(32):
			for vertex: Vector3 in [rings[i][j],rings[i+1][j+1],rings[i][j+1],rings[i][j],rings[i+1][j],rings[i+1][j+1]]:shell.add_vertex(vertex)
	for j in range(32):
		for vertex: Vector3 in [stations[0].centre,rings[0][j],rings[0][j+1],stations[-1].centre,rings[-1][j+1],rings[-1][j]]:shell.add_vertex(vertex)
	shell.generate_normals()
	_add_arm_part(fixture,"SingleArmHousing",shell.commit(),metal,id,height,false)
	# A solid opal lens projects slightly beyond the metal edge. Its luminous
	# side lip remains readable from the elevated courtyard review camera.
	var panel_centre := (arm_start+along*0.88+underside*0.09)*size
	var panel := PackedVector3Array()
	for j in range(49):
		var angle := TAU*float(j)/48.0
		var u := signf(cos(angle))*pow(absf(cos(angle)),0.35)
		var v := signf(sin(angle))*pow(absf(sin(angle)),0.35)
		panel.append(panel_centre+along*(0.70*u*size)+across*(0.28*v*size))
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	var depth := underside*(0.12*size)
	for j in range(48):
		for vertex: Vector3 in [panel_centre,panel[j],panel[j+1],panel_centre+depth,panel[j+1]+depth,panel[j]+depth,panel[j],panel[j]+depth,panel[j+1]+depth,panel[j],panel[j+1]+depth,panel[j+1]]:surface.add_vertex(vertex)
	surface.generate_normals()
	var part := _add_arm_part(fixture,"Diffuser",surface.commit(),lens,id,height,true)

	var emitter := panel_centre+underside*(0.15*size)
	var aim := focus-point
	# Broad overlapping cones cover the full paving, including its tips and
	# connecting edges. The centre remains the shared physical aiming point.
	var beam_angle := deg_to_rad(70.0)
	var beam_reach := reach
	var extras: Dictionary = part.get_meta("extras")
	extras["design_lights"] = [{"type":"spot","position":[emitter.x,emitter.y,emitter.z],"target":[aim.x,aim.y,aim.z],"color":0xffdfb5,"intensity":energy*0.75*PI,"distance":beam_reach,"angle":beam_angle,"attenuation":0.7,"angle_attenuation":0.65}]
	part.set_meta("extras",extras)

func _add_arm_part(parent: Node3D, label: String, mesh: ArrayMesh, material: Material, id: String, height: float, diffuse: bool) -> MeshInstance3D:
	mesh.surface_set_material(0,material)
	var part := MeshInstance3D.new()
	part.name = label
	part.mesh = mesh
	part.set_meta("extras",{"outdoor_fixture_id":id,"outdoor_fixture_group":"high","lighting_diffuser":diffuse,"full_height":true,"furniture":false,"height":height})
	parent.add_child(part)
	return part

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
