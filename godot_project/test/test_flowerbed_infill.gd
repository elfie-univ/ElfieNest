extends SceneTree
## Check the actual saved flower instances against the imported ground surfaces.
const BINDING := preload("res://nest/assembly/glb_placement.gd")
const POSES := preload("res://test/test_lotus_bay.gd")
const GROUND := "res://nest/courtyard/parts/ground/shared-ground.glb"
const PLANTS := "res://nest/courtyard/parts/shared/plant-library.glb"
const EXPECTED := {"meadow_inner":20,"ring_join":4,"waterside_rear":21}
const FAMILIES := {"part_00005":["part_00005","part_00006","part_00007","part_00008"],"part_00009":["part_00009","part_00010","part_00011"],"part_00012":["part_00012","part_00013","part_00014","part_00015"]}
static var mask: Dictionary={}
static var radii: Dictionary={}

func _initialize() -> void:call_deferred("run")

static func prepare_mask() -> void:
	if not mask.is_empty():return
	var scene: Node3D=(load(GROUND) as PackedScene).instantiate()
	for node: MeshInstance3D in scene.find_children("*","MeshInstance3D",true,false):
		var body: bool=str(node.get_meta("extras",{}).get("source_name","")).begins_with("COMPLETE Building garden island")
		var pose:=POSES.pose_in(scene,node)
		for surface: int in node.mesh.get_surface_count():
			var material: Material=node.mesh.surface_get_material(surface)
			var soil: bool=body and "Lake and garden soil" in material.resource_name
			var arrays:=node.mesh.surface_get_arrays(surface)
			var points: PackedVector3Array=arrays[Mesh.ARRAY_VERTEX]
			var indices: PackedInt32Array=arrays[Mesh.ARRAY_INDEX]
			for at: int in range(0,indices.size(),3):
				var a:=pose*points[indices[at]]
				var b:=pose*points[indices[at+1]]
				var c:=pose*points[indices[at+2]]
				if maxf(a.y,maxf(b.y,c.y))<-.10 or minf(a.y,minf(b.y,c.y))>.35:continue
				var denominator: float=(float(b.z)-c.z)*(float(a.x)-c.x)+(float(c.x)-b.x)*(float(a.z)-c.z)
				if absf(denominator)<0.0000000001:continue
				var row:=[a,b,c,denominator,soil]
				for x: int in range(floori(minf(a.x,minf(b.x,c.x))),floori(maxf(a.x,maxf(b.x,c.x)))+1):
					for z: int in range(floori(minf(a.z,minf(b.z,c.z))),floori(maxf(a.z,maxf(b.z,c.z)))+1):
						var key:=Vector2i(x,z)
						if not mask.has(key):mask[key]=[]
						mask[key].append(row)
	scene.free()
	var plants: Node3D=(load(PLANTS) as PackedScene).instantiate()
	for base: String in FAMILIES:
		var radius:=0.0
		for source: String in FAMILIES[base]:
			var node:=plants.find_child(source,true,false) as MeshInstance3D
			for surface: int in node.mesh.get_surface_count():
				var points: PackedVector3Array=node.mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
				for point: Vector3 in points:radius=maxf(radius,Vector2(point.x,point.z).length())
		radii[base]=radius
	plants.free()

static func is_soil(x: float,z: float) -> bool:
	var height:=-INF
	var soil:=false
	for row: Array in mask.get(Vector2i(floori(x),floori(z)),[]):
		var a: Vector3=row[0]
		var b: Vector3=row[1]
		var c: Vector3=row[2]
		var u: float=((float(b.z)-c.z)*(x-c.x)+(float(c.x)-b.x)*(z-c.z))/float(row[3])
		var v: float=((float(c.z)-a.z)*(x-c.x)+(float(a.x)-c.x)*(z-c.z))/float(row[3])
		if minf(u,minf(v,1.0-u-v))<-.000001:continue
		var y: float=u*a.y+v*b.y+(1.0-u-v)*c.y
		if y>height+0.00000001 or (absf(y-height)<0.00000001 and not row[4]):
			height=y
			soil=bool(row[4])
	return soil and height>-.09 and height<.1

static func verify(tree: SceneTree) -> Dictionary:
	var zones:={"meadow_inner":0,"ring_join":0,"waterside_rear":0}
	var components:=0
	for area: String in ["ground","forest","meadow","waterside"]:
		var file_name:= "courtyard-ground" if area=="ground" else area+"-layout"
		var scene: Node3D=(load("res://nest/courtyard/areas/%s/%s.scn" % [area,file_name]) as PackedScene).instantiate()
		tree.root.add_child(scene)
		for node: MultiMeshInstance3D in scene.find_children("*","MultiMeshInstance3D",true,false):
			if not bool(node.get_meta("flowerbed_infill",false)):continue
			var parent:=node.get_parent()
			var slot:=node.get_index()
			if parent.get_script()!=BINDING or parent.library.resource_path!=PLANTS or node.multimesh==null or node.multimesh.mesh==null:
				scene.free()
				return {"error":"An infill flower lost its shared prototype"}
			components+=1
			var source:=str(parent.source_nodes[slot])
			if not FAMILIES.has(source):continue
			prepare_mask()
			var data: Dictionary=parent.instance_batches[slot]
			var buffer: PackedFloat32Array=data.buffer
			var labels: PackedStringArray=node.get_meta("infill_zones")
			if buffer.size()!=int(data.instance_count)*12 or labels.size()!=int(data.instance_count):
				scene.free()
				return {"error":"Infill instances or zone labels are incomplete"}
			for i: int in int(data.instance_count):
				var at:=i*12
				var local:=Transform3D(Basis(Vector3(buffer[at],buffer[at+4],buffer[at+8]),Vector3(buffer[at+1],buffer[at+5],buffer[at+9]),Vector3(buffer[at+2],buffer[at+6],buffer[at+10])),Vector3(buffer[at+3],buffer[at+7],buffer[at+11]))
				var pose:=POSES.pose_in(scene,node)*local
				var radius: float=radii[source]*maxf(pose.basis.x.length(),pose.basis.z.length())
				for j: int in 16:
					var angle:=float(j)*TAU/16.0
					if not is_soil(pose.origin.x+radius*cos(angle),pose.origin.z+radius*sin(angle)):
						scene.free()
						return {"error":"A new flower overlaps lawn, forest, water or paving","position":str(pose.origin),"source":source}
				if not zones.has(labels[i]):
					scene.free()
					return {"error":"Unknown infill zone"}
				zones[labels[i]]+=1
		scene.free()
	if zones!=EXPECTED:return {"error":"A marked flowerbed strip was not filled","zones":zones}
	return {"error":"","zones":zones,"clumps":45,"shared_component_batches":components,"all_canopy_samples_on_flowerbed_soil":true}

func run() -> void:
	var result:=verify(self)
	if not str(result.error).is_empty():
		push_error(JSON.stringify(result))
		quit(1)
		return
	print("FLOWERBED_INFILL_OK ",JSON.stringify(result))
	quit(0)
