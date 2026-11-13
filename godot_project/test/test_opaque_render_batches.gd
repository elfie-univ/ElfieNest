extends SceneTree
const SCRIPT := "res://nest/rendering/estate_opaque_batches.gd"
var failures := 0

func _initialize() -> void: call_deferred("run")

func check(value: bool, message: String) -> void:
	if not value: failures += 1; push_error(message)

func part(parent: Node3D, offset: float, material: Material, lod: bool = false) -> MeshInstance3D:
	var arrays := []; arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3(offset,0,0),Vector3(offset+0.15,0,0),Vector3(offset,0,0.15)])
	arrays[Mesh.ARRAY_NORMAL] = PackedVector3Array([Vector3.UP,Vector3.UP,Vector3.UP])
	arrays[Mesh.ARRAY_TEX_UV] = PackedVector2Array([Vector2.ZERO,Vector2.RIGHT,Vector2.UP])
	arrays[Mesh.ARRAY_COLOR] = PackedColorArray([Color.RED,Color.GREEN,Color.BLUE])
	arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0,1,2])
	if lod:
		arrays[Mesh.ARRAY_VERTEX].append(Vector3(offset+0.15,0,0.15))
		arrays[Mesh.ARRAY_NORMAL].append(Vector3.UP)
		arrays[Mesh.ARRAY_TEX_UV].append(Vector2.ONE)
		arrays[Mesh.ARRAY_COLOR].append(Color.WHITE)
		arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0,1,2,1,3,2])
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays,[],{0.1:PackedInt32Array([0,1,2])} if lod else {})
	mesh.surface_set_material(0,material)
	mesh.set_meta("nest_source_library","res://nest/courtyard/parts/ground/shared-ground.glb")
	var node := MeshInstance3D.new(); node.mesh = mesh; parent.add_child(node)
	return node

func run() -> void:
	if not ResourceLoader.exists(SCRIPT):
		push_error("Missing opaque batches: equal static surfaces still require separate draws")
		quit(1); return
	var world := Node3D.new(); root.add_child(world)
	var material := StandardMaterial3D.new()
	var first := part(world,0.0,material)
	var second := part(world,0.3,material.duplicate())
	var other_layer := part(world,0.6,material); other_layer.layers = 2
	var translucent := material.duplicate() as StandardMaterial3D
	translucent.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	var glass := part(world,0.9,translucent)
	var detailed := part(world,1.2,material,true)
	check(not detailed.mesh.get("_surfaces")[0].get("lods",[]).is_empty(),"Fixture must contain an actual reduced LOD")
	var moving := part(world,1.5,material); moving.set_meta("extras",{"door_leaf":true})
	var before := [first.mesh,second.mesh]
	var batcher: Node = load(SCRIPT).new(); world.add_child(batcher); batcher.bind(world)
	check(batcher.groups.size()==1,"Only compatible opaque static surfaces may join")
	if failures: world.free(); quit(1); return
	var draw: MeshInstance3D = batcher.groups[0].draw
	var actual := draw.mesh.surface_get_arrays(0)
	for slot in [Mesh.ARRAY_VERTEX,Mesh.ARRAY_NORMAL,Mesh.ARRAY_TEX_UV,Mesh.ARRAY_COLOR]:
		var expected: Variant = before[0].surface_get_arrays(0)[slot].duplicate()
		expected.append_array(before[1].surface_get_arrays(0)[slot])
		check(var_to_bytes(actual[slot])==var_to_bytes(expected),"Batch changed a decoded vertex attribute: "+str(slot))
	check(actual[Mesh.ARRAY_INDEX]==PackedInt32Array([0,1,2,3,4,5]),"Batch changed triangle order")
	check(first.mesh==before[0] and second.mesh==before[1],"Source meshes must retain their identity")
	check(first.layers==0 and second.layers==0 and draw.layers==1,"Batch must replace only the original draws")
	check(other_layer.layers==2 and glass.layers==1 and detailed.layers==1 and moving.layers==1,"Layer, transparency, LOD and movement exclusions must remain drawn")
	batcher.set_enabled(false)
	check(first.layers==1 and second.layers==1 and not draw.visible,"Disabling batches must restore sources")
	batcher.set_enabled(true)
	check(first.layers==0 and draw.visible,"Re-enabling unchanged sources must be reversible")
	second.mesh = before[0]
	batcher._process(0.0)
	check(first.layers==1 and second.layers==1 and not draw.visible,"A replaced mesh must immediately fall back to its original draw")
	world.free()
	var lit := Node3D.new(); root.add_child(lit)
	var near := part(lit,0.0,material); var far := part(lit,0.6,material)
	var light := OmniLight3D.new(); light.omni_range = 0.2; lit.add_child(light)
	var controlled: Node = load(SCRIPT).new(); lit.add_child(controlled); controlled.bind(lit)
	check(controlled.groups.is_empty() and near.layers==1 and far.layers==1,"Different potential local-light sets must not be combined")
	lit.free()
	check_shared_mesh()
	check_material_sharing("res://nest/rendering/estate_opaque.gdshader")
	check_material_sharing("res://nest/furniture/shared/bedroom/m01_sheen.gdshader")
	print("OPAQUE_BATCHES failures=",failures)
	quit(0 if failures==0 else 1)

func check_shared_mesh() -> void:
	var world := Node3D.new(); root.add_child(world)
	var first := part(world,0.0,StandardMaterial3D.new())
	var second := MeshInstance3D.new(); second.mesh = first.mesh; world.add_child(second)
	var batcher: Node = load(SCRIPT).new(); world.add_child(batcher); batcher.bind(world)
	check(batcher.groups.size()==1,"Shared mesh instances must form one compatible batch")
	var connections := first.mesh.changed.get_connections().filter(func(connection: Dictionary) -> bool: return connection.callable.get_object()==batcher)
	check(connections.size()==1,"A shared resource must have exactly one invalidation connection per batch")
	first.mesh.emit_changed()
	check(first.layers==1 and second.layers==1 and not batcher.groups[0].draw.visible,"Changing a shared mesh must restore every original instance")
	world.free()

func check_material_sharing(shader_path: String) -> void:
	var world := Node3D.new(); root.add_child(world)
	var source := ShaderMaterial.new()
	source.shader = load(shader_path)
	source.resource_name = "Shared opaque fixture"
	source.set_shader_parameter("source_albedo",Color(0.2,0.4,0.1))
	var first := part(world,0.0,source)
	var second := part(world,0.3,source.duplicate())
	var other_room := part(world,0.6,source.duplicate())
	var different := source.duplicate() as ShaderMaterial
	different.set_shader_parameter("source_roughness",0.9)
	var rough := part(world,0.9,different)
	for node: MeshInstance3D in [first,second,rough]: node.set_meta("extras",{"module":"M01"})
	other_room.set_meta("extras",{"module":"M02"})
	var controller: RefCounted = load("res://nest/rendering/estate_lighting_sample.gd").new()
	controller.bind_m01(world)
	check(first.get_active_material(0)==second.get_active_material(0),"Equivalent opaque materials in one lighting group must share a runtime material")
	check(first.get_active_material(0)!=other_room.get_active_material(0) and first.get_active_material(0)!=rough.get_active_material(0),"Room ownership and different shader inputs must stay separate")
	check(first.get_active_material(0)!=source,"Sharing must not mutate imported materials")
	controller.set_opaque_shared(false)
	check(first.get_active_material(0)!=second.get_active_material(0),"Comparison must restore the original independent grouping")
	controller.set_opaque_shared(true)
	check(first.get_active_material(0)==second.get_active_material(0),"Shared GPU state must be reversible")
	controller.apply_environment(0.0,false)
	check(first.get_active_material(0).get_shader_parameter("natural_light_scale")==second.get_active_material(0).get_shader_parameter("natural_light_scale"),"Shared opaque surfaces must retain the natural-light switch")
	world.free()
