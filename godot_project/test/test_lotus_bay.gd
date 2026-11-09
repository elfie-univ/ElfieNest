extends SceneTree
## Verify that the assembled lotus batches use every placement from the lake GLB.

const BINDING := preload("res://nest/assembly/glb_placement.gd")
const LAKE := "res://nest/courtyard/parts/waterside/lake.glb"
const AREA := "res://nest/courtyard/areas/waterside/waterside-layout.scn"
const GARDEN := "res://nest/courtyard/overview/courtyard-all/courtyard-layout.scn"
const COUNTS := {"float_deep":15,"float_mid":14,"low_deep":37,"low_mid":27,"high":14,"rolled":4,"blooms":10,"buds":6}

func _initialize() -> void:
	call_deferred("run")

static func pose_in(scene_root: Node3D, node: Node3D) -> Transform3D:
	var pose:=node.transform
	var parent:=node.get_parent() as Node3D
	while parent!=null and parent!=scene_root:
		pose=parent.transform*pose
		parent=parent.get_parent() as Node3D
	return pose

static func stem_faces_outward(mesh: Mesh) -> bool:
	var right:=-INF
	var direction:=Vector3.ZERO
	for surface: int in mesh.get_surface_count():
		var arrays:=mesh.surface_get_arrays(surface)
		var points: PackedVector3Array=arrays[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array=arrays[Mesh.ARRAY_NORMAL]
		for i: int in points.size():
			if points[i].y<0.0001 and points[i].x>right:
				right=points[i].x
				direction=normals[i]
	return right>0.0 and direction.x>0.4

static func verify_scene(scene: Node3D) -> Dictionary:
	var library: Node3D=(load(LAKE) as PackedScene).instantiate()
	var groups:={}
	for leaf: MeshInstance3D in library.find_children("*","MeshInstance3D",true,false):
		var extras: Dictionary=leaf.get_meta("extras",{})
		if not extras.has("lotus_batch"):continue
		if str(extras.lotus_role) in ["bloom","bud"] and not stem_faces_outward(leaf.mesh):
			library.free()
			return {"error":"An imported flower stem has inward normals"}
		var group:=str(extras.lotus_batch)
		if not groups.has(group):groups[group]=[]
		groups[group].append({"mesh":leaf.mesh,"pose":pose_in(library,leaf)})
	var actual:={}
	var instances:=0
	for batch: MultiMeshInstance3D in scene.find_children("*","MultiMeshInstance3D",true,false):
		var group:=str(batch.get_meta("lotus_batch",""))
		if group.is_empty():continue
		if actual.has(group) or not groups.has(group):
			library.free()
			return {"error":"A lotus batch is duplicated or unknown"}
		var parent:=batch.get_parent()
		if parent.get_script()!=BINDING or parent.library.resource_path!=LAKE or batch.multimesh==null:
			library.free()
			return {"error":"A lotus batch lost its lake prototype"}
		var data: MultiMesh=batch.multimesh
		if data.mesh!=groups[group][0].mesh or data.instance_count!=groups[group].size():
			library.free()
			return {"error":"Lotus geometry or instance count differs from its GLB"}
		# A headless dummy renderer returns identity for GPU transform readback.
		# Validate the saved canonical buffer; the browser checks rendered placement.
		var saved: Dictionary=parent.instance_batches.get(batch.get_index(),{})
		var buffer: PackedFloat32Array=saved.get("buffer",PackedFloat32Array())
		if saved.get("transform_format")!=MultiMesh.TRANSFORM_3D or buffer.size()!=data.instance_count*12:
			library.free()
			return {"error":"The saved lotus instance buffer is incomplete"}
		for i: int in data.instance_count:
			var at:=i*12
			var basis:=Basis(Vector3(buffer[at],buffer[at+4],buffer[at+8]),Vector3(buffer[at+1],buffer[at+5],buffer[at+9]),Vector3(buffer[at+2],buffer[at+6],buffer[at+10]))
			var instance_pose:=Transform3D(basis,Vector3(buffer[at+3],buffer[at+7],buffer[at+11]))
			var pose:=pose_in(scene,batch)*instance_pose
			if not pose.is_equal_approx(groups[group][i].pose):
				var detail:={"error":"An assembled lotus moved away from its GLB placement","group":group,"instance":i,"actual":str(pose),"expected":str(groups[group][i].pose)}
				library.free()
				return detail
		actual[group]=data.instance_count
		instances+=data.instance_count
	library.free()
	if actual!=COUNTS:return {"error":"Lotus leaf, bloom or bud counts changed","actual":actual}
	return {"error":"","batches":actual,"instances":instances,"shared_plant_meshes":8}

static func verify(tree: SceneTree) -> Dictionary:
	var rows:=[]
	for path: String in [AREA,GARDEN]:
		var scene: Node3D=(load(path) as PackedScene).instantiate()
		tree.root.add_child(scene)
		var result:=verify_scene(scene)
		scene.free()
		if not str(result.error).is_empty():return result
		rows.append({"scene":path,"result":result})
	return {"error":"","scenes":rows}

func run() -> void:
	var result:=verify(self)
	if not str(result.error).is_empty():
		push_error(JSON.stringify(result))
		quit(1)
		return
	print("LOTUS_BAY_ASSEMBLY_OK ",JSON.stringify(result))
	quit(0)
