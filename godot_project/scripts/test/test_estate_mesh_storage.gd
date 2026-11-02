extends SceneTree
const STORAGE := preload("res://rooms/estate/estate_mesh_storage.gd")
func _initialize() -> void: call_deferred("run")
func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok
func run() -> void:
	var world := Node3D.new()
	root.add_child(world)
	var template := BoxMesh.new()
	var red := StandardMaterial3D.new()
	red.albedo_color=Color.RED
	var blue := StandardMaterial3D.new()
	blue.albedo_color=Color.BLUE
	var nodes: Array[MeshInstance3D]=[]
	for i in range(3):
		var node := MeshInstance3D.new()
		var mesh := ArrayMesh.new()
		var arrays := template.surface_get_arrays(0)
		if i==2:
			var positions: PackedVector3Array=arrays[Mesh.ARRAY_VERTEX]
			positions[0].x+=0.001
			arrays[Mesh.ARRAY_VERTEX]=positions
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
		mesh.surface_set_material(0,red if i==0 else blue)
		mesh.surface_set_name(0,"Authored material %d" % i)
		node.mesh=mesh
		node.position=Vector3(i,0,0)
		node.layers=1<<i
		world.add_child(node)
		nodes.append(node)
	var overlay := StandardMaterial3D.new()
	overlay.albedo_color=Color.GREEN
	nodes[1].material_override=overlay
	var result := STORAGE.share_geometry(world)
	if not require(result.meshes_shared==1 and nodes[0].mesh==nodes[1].mesh,"Identical geometry with different materials must share its buffers"):return
	if not require(nodes[2].mesh!=nodes[0].mesh,"Even a small geometry difference must remain distinct"):return
	if not require(nodes[1].get_active_material(0)==overlay,"Whole-mesh overrides must remain unchanged"):return
	nodes[1].material_override=null
	if not require(nodes[0].get_active_material(0)==red and nodes[1].get_active_material(0)==blue,"Per-surface authored materials must remain unchanged after clearing an override"):return
	for i in range(3):
		if not require(nodes[i].position==Vector3(i,0,0) and nodes[i].layers==1<<i,"Transforms and light masks must remain unchanged"):return
	if not require(STORAGE.share_geometry(world).meshes_shared==0,"Sharing must be idempotent"):return
	var prototype := MeshInstance3D.new()
	prototype.name="__ELFIE_INST_GROUP_test"
	prototype.mesh=nodes[0].mesh.duplicate()
	world.add_child(prototype)
	STORAGE.share_geometry(world,true)
	if not require(prototype.mesh!=nodes[0].mesh,"Import must preserve independently bound MultiMesh prototype materials"):return
	prototype.name="BoundCloth"
	prototype.set_meta("estate_bedding_layers",true)
	STORAGE.share_geometry(world)
	if not require(prototype.mesh!=nodes[0].mesh,"Animated bedding must retain its original rest-pose mesh identity"):return
	var pixels := Image.create(4,4,false,Image.FORMAT_RGBA8)
	pixels.fill(Color.RED)
	red.albedo_texture=ImageTexture.create_from_image(pixels)
	blue.albedo_texture=ImageTexture.create_from_image(pixels)
	pixels.set_pixel(0,0,Color.BLUE)
	red.normal_texture=ImageTexture.create_from_image(pixels)
	if not require(STORAGE.share_textures(world)==1,"Only byte-identical textures should share storage"):return
	if not require(red.albedo_texture==blue.albedo_texture and red.normal_texture!=red.albedo_texture,"Distinct pixels and texture roles must remain intact"):return
	if not require(red.normal_texture.get_image().get_pixel(0,0)==Color.BLUE,"Texture pixels must not change during sharing"):return
	world.free()
	print("PASS exact geometry sharing preserves material, geometry differences, transforms and masks")
	quit()
