extends Node3D

@export var bed_count: int = 11

var room_width_per_module = 10.0
var room_depth = 12.0

# Preload Kenney models
var desk_model = preload("res://assets/kenney_furniture/Models/GLTF format/desk.glb")
var chair_model = preload("res://assets/kenney_furniture/Models/GLTF format/chairDesk.glb")
var bed_model = preload("res://assets/kenney_furniture/Models/GLTF format/bedSingle.glb")
var wardrobe_model = preload("res://assets/kenney_furniture/Models/GLTF format/bookcaseClosedDoors.glb")
var wall_model = preload("res://assets/kenney_furniture/Models/GLTF format/wall.glb")
var table_round = preload("res://assets/kenney_furniture/Models/GLTF format/tableRound.glb")
var table_long = preload("res://assets/kenney_furniture/Models/GLTF format/table.glb")
var sofa = preload("res://assets/kenney_furniture/Models/GLTF format/loungeSofa.glb")
var tv = preload("res://assets/kenney_furniture/Models/GLTF format/televisionModern.glb")
var laptop = preload("res://assets/kenney_furniture/Models/GLTF format/laptop.glb")

func _ready():
	call_deferred("generate_room", bed_count)
	setup_camera()

func setup_camera():
	var camera = Camera3D.new()
	add_child(camera)
	# Give a wide isometric-like top-down view
	camera.position = Vector3(0, 18, 12)
	camera.rotation_degrees = Vector3(-55, 0, 0)
	camera.current = true
	
	# Save screenshot after rendering
	get_tree().create_timer(1.0).timeout.connect(save_screenshot)

func save_screenshot():
	var image = get_viewport().get_texture().get_image()
	image.save_png("res://dorm_preview_kenney.png")
	print("Screenshot saved to res://dorm_preview_kenney.png")
	get_tree().quit()

func generate_room(count: int):
	for child in get_children():
		if child is not Camera3D and child is not DirectionalLight3D:
			child.queue_free()
			
	var num_modules = max(1, ceil(count / 4.0))
	var total_width = num_modules * room_width_per_module
	
	# Position camera to see all modules
	var cam = get_viewport().get_camera_3d()
	if cam:
		cam.position = Vector3(total_width / 2.0 - room_width_per_module/2.0, 15 + num_modules * 1.5, 12 + num_modules)
		cam.rotation_degrees = Vector3(-55, 0, 0)
	
	# Floor (simple CSG for large area, as Kenney floor tiles are small)
	var floor_csg = CSGBox3D.new()
	floor_csg.size = Vector3(total_width + 2, 0.2, room_depth + 4)
	floor_csg.position = Vector3(total_width / 2.0 - room_width_per_module/2.0, -0.1, -2)
	var mat_floor = StandardMaterial3D.new()
	mat_floor.albedo_color = Color(0.85, 0.88, 0.9)
	floor_csg.material = mat_floor
	add_child(floor_csg)
	
	# Wormhole portal on the left
	create_wormhole(Vector3(-room_width_per_module/2.0 - 2, 0, 0))
	
	var beds_created = 0
	for m in range(num_modules):
		var offset_x = m * room_width_per_module
		
		# Room boundaries
		create_walls(offset_x)
		
		# Public zone at the top of the module
		create_public_zone(m, offset_x)
		
		# 4 beds per module (01, 02 on left; 03, 04 on right)
		var positions = [
			Vector3(offset_x - 3, 0, 0),    # Top Left (01)
			Vector3(offset_x - 3, 0, 3),    # Bottom Left (02)
			Vector3(offset_x + 3, 0, 0),    # Top Right (03)
			Vector3(offset_x + 3, 0, 3)     # Bottom Right (04)
		]
		
		# Rotations so they face the internal corridor
		var rotations = [90, 90, -90, -90]
		
		for i in range(4):
			if beds_created < count:
				create_bed_desk_combo("bed_%d" % (beds_created + 1), positions[i], rotations[i])
				beds_created += 1

func create_walls(offset_x: float):
	# Left wall of the room
	for z in range(-3, 6, 2):
		var wall = wall_model.instantiate()
		wall.position = Vector3(offset_x - 4.5, 0, z)
		wall.rotation_degrees = Vector3(0, 90, 0)
		add_child(wall)
	# Right wall of the room
	for z in range(-3, 6, 2):
		var wall = wall_model.instantiate()
		wall.position = Vector3(offset_x + 4.5, 0, z)
		wall.rotation_degrees = Vector3(0, 90, 0)
		add_child(wall)

func create_wormhole(pos: Vector3):
	var portal = CSGCylinder3D.new()
	portal.radius = 1.5
	portal.height = 0.1
	portal.position = pos
	var mat = StandardMaterial3D.new()
	mat.albedo_color = Color(0.5, 0.0, 1.0)
	mat.emission_enabled = true
	mat.emission = Color(0.8, 0.2, 1.0)
	mat.emission_energy_multiplier = 2.0
	portal.material = mat
	add_child(portal)

func create_public_zone(module_idx: int, offset_x: float):
	# Public zone is at Z = -4
	var zone_type = module_idx % 4
	var pos = Vector3(offset_x, 0, -4)
	
	if zone_type == 0:
		# Leisure round table
		var table = table_round.instantiate()
		table.position = pos
		add_child(table)
		for i in range(4):
			var c = chair_model.instantiate()
			c.position = pos + Vector3(cos(i*PI/2)*1.5, 0, sin(i*PI/2)*1.5)
			c.rotation_degrees = Vector3(0, -i*90 - 90, 0)
			add_child(c)
	elif zone_type == 1:
		# Dining area (long table)
		var table = table_long.instantiate()
		table.position = pos
		add_child(table)
		for i in [-1, 0, 1]:
			var c1 = chair_model.instantiate()
			c1.position = pos + Vector3(i*1.0, 0, 1.2)
			c1.rotation_degrees = Vector3(0, 180, 0)
			add_child(c1)
			var c2 = chair_model.instantiate()
			c2.position = pos + Vector3(i*1.0, 0, -1.2)
			c2.rotation_degrees = Vector3(0, 0, 0)
			add_child(c2)
	elif zone_type == 2:
		# Quiet study
		for i in [-1.5, 1.5]:
			var d = desk_model.instantiate()
			d.position = pos + Vector3(i, 0, -0.5)
			add_child(d)
			var l = laptop.instantiate()
			l.position = pos + Vector3(i, 0.75, -0.5)
			add_child(l)
			var c = chair_model.instantiate()
			c.position = pos + Vector3(i, 0, 0.5)
			add_child(c)
	else:
		# AV room
		var s = sofa.instantiate()
		s.position = pos + Vector3(0, 0, 1)
		add_child(s)
		var t = tv.instantiate()
		t.position = pos + Vector3(0, 0.5, -1)
		t.rotation_degrees = Vector3(0, 180, 0)
		add_child(t)

func create_bed_desk_combo(id: String, pos: Vector3, rot_y: float):
	var group = Node3D.new()
	group.name = id
	group.position = pos
	group.rotation_degrees = Vector3(0, rot_y, 0)
	
	# Desk at bottom
	var desk_inst = desk_model.instantiate()
	desk_inst.position = Vector3(0, 0, 0)
	group.add_child(desk_inst)
	
	var chair = chair_model.instantiate()
	chair.position = Vector3(0, 0, 0.8)
	group.add_child(chair)
	
	var lap = laptop.instantiate()
	lap.position = Vector3(0, 0.75, 0)
	group.add_child(lap)
	
	# Wardrobe next to desk
	var wardrobe = wardrobe_model.instantiate()
	wardrobe.position = Vector3(-1.2, 0, 0)
	group.add_child(wardrobe)
	
	# Bed on top (elevated)
	var bed = bed_model.instantiate()
	bed.position = Vector3(-0.6, 1.8, 0) # elevated
	group.add_child(bed)
	
	# Pillars to support bed
	for px in [-1.6, 0.4]:
		for pz in [-0.5, 0.5]:
			var leg = CSGCylinder3D.new()
			leg.radius = 0.05
			leg.height = 1.8
			leg.position = Vector3(px, 0.9, pz)
			var mat = StandardMaterial3D.new()
			mat.albedo_color = Color(0.3, 0.3, 0.3)
			leg.material = mat
			group.add_child(leg)
			
	# Ladder
	var ladder = CSGBox3D.new()
	ladder.size = Vector3(0.1, 1.8, 0.4)
	ladder.position = Vector3(0.4, 0.9, 0)
	var mat_ladder = StandardMaterial3D.new()
	mat_ladder.albedo_color = Color(0.8, 0.5, 0.2)
	ladder.material = mat_ladder
	group.add_child(ladder)
	
	add_child(group)
