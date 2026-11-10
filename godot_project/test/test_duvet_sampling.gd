extends SceneTree
## Keep cloth topology, vertices, normals and material while avoiding duplicate work.
const DUVET := preload("res://runtime/actor/authored_duvet.gd")
var changes := 0

func _initialize() -> void:
	create_timer(30.0).timeout.connect(func() -> void: push_error("Cloth sampling check timed out"); quit(1))
	call_deferred("run")

func run() -> void:
	var arrays := []; arrays.resize(Mesh.ARRAY_MAX)
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var indices := PackedInt32Array()
	for z in range(49):
		for x in range(33):
			vertices.append(Vector3(float(x)/32.0-0.5, 0.36, float(z)/24.0-1.0))
			normals.append(Vector3.UP)
	for z in range(48):
		for x in range(32):
			var a := z*33+x
			indices.append_array(PackedInt32Array([a,a+33,a+1, a+1,a+33,a+34]))
	arrays[Mesh.ARRAY_VERTEX] = vertices; arrays[Mesh.ARRAY_NORMAL] = normals; arrays[Mesh.ARRAY_INDEX] = indices
	var resource := ArrayMesh.new(); resource.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	resource.set_meta("estate_duvet_rest", true)
	var material := StandardMaterial3D.new(); resource.surface_set_material(0, material)
	var cloth := MeshInstance3D.new(); cloth.mesh = resource; root.add_child(cloth)
	var duvet := DUVET.new(); duvet.bind(cloth)
	duvet._posed = vertices.duplicate(); duvet._folded = vertices.duplicate(); duvet._folded_empty = vertices.duplicate()
	for i in range(vertices.size()):
		duvet._posed[i].y += 0.1*cos(vertices[i].x*PI)
		duvet._folded[i].z += 0.2
	var started := Time.get_ticks_usec()
	for frame in range(24):
		var cover := float(frame)/24.0
		duvet.sample(cover, 1.0, 0.02, 0.003, 0.8)
		var actual: Array = cloth.mesh.surface_get_arrays(0)
		var points: PackedVector3Array = actual[Mesh.ARRAY_VERTEX]
		for i in range(vertices.size()):
			var expected: Vector3 = duvet._folded_empty[i].lerp(duvet._folded[i], 0.8).lerp(duvet._posed[i], cover)
			var u := (vertices[i].z+1.0)/2.0
			expected.y += 0.02*(1.0-u)+0.003*sin(u*PI)*cover
			if not points[i].is_equal_approx(expected):
				push_error("Cloth optimization changed the sampled surface"); quit(1); return
		if actual[Mesh.ARRAY_INDEX] != indices or cloth.mesh.surface_get_material(0) != material:
			push_error("Cloth optimization changed topology or material"); quit(1); return
	print("DUVET_SAMPLE_US ", (Time.get_ticks_usec()-started)/24.0)
	duvet.sample(1.0, 0.0, 0.0, 0.002, 1.0)
	cloth.mesh.changed.connect(func() -> void: changes += 1)
	duvet.sample(1.0, 0.0, 0.0, 0.002, 1.0)
	if changes != 0:
		push_error("Identical cloth sample rebuilt its mesh"); quit(1); return
	changes = 0
	duvet.sample(0.7, 1.0, 0.02, 0.003, 0.8, true)
	var pending := duvet.points()
	var target := pending[0]+Vector3(0.01,0.02,0.03)
	duvet.pin_grip(0,target,1.0,true)
	if changes != 0 or not duvet.points()[0].is_equal_approx(target):
		push_error("Held hem did not stay in the deferred cloth sample"); quit(1); return
	duvet.commit()
	if changes == 0:
		push_error("Deferred cloth sample was never uploaded"); quit(1); return
	changes = 0
	duvet.commit()
	if changes != 0:
		push_error("Cloth sample uploaded twice"); quit(1); return
	var reference_path := OS.get_environment("ELFIENEST_DUVET_REFERENCE")
	if not reference_path.is_empty():
		if not FileAccess.file_exists(reference_path):
			push_error("Recorded cloth baseline does not exist: "+reference_path); quit(1); return
		var script := GDScript.new(); script.source_code = FileAccess.get_file_as_string(reference_path)
		if script.reload() != OK:
			push_error("Could not load the recorded cloth benchmark baseline"); quit(1); return
		var baseline: RefCounted = script.new()
		var old_cloth := MeshInstance3D.new(); old_cloth.mesh = resource; root.add_child(old_cloth)
		baseline.bind(old_cloth)
		baseline._posed = duvet._posed; baseline._folded = duvet._folded; baseline._folded_empty = duvet._folded_empty
		var before_us := 0; var after_us := 0
		for frame in range(48):
			var cover := 0.2+float(frame)/80.0
			var clock := Time.get_ticks_usec()
			baseline.sample(cover,1.0,0.02,0.003,0.8)
			var old_points: PackedVector3Array = old_cloth.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
			var grip := old_points[0]+Vector3(0.01,0.02,0.03)
			baseline.pin_grip(0,grip,1.0)
			before_us += Time.get_ticks_usec()-clock
			clock = Time.get_ticks_usec()
			duvet.sample(cover,1.0,0.02,0.003,0.8,true)
			duvet.pin_grip(0,grip,1.0,true); duvet.commit()
			after_us += Time.get_ticks_usec()-clock
			var old_arrays: Array = old_cloth.mesh.surface_get_arrays(0)
			var new_arrays: Array = cloth.mesh.surface_get_arrays(0)
			for slot in [Mesh.ARRAY_VERTEX,Mesh.ARRAY_NORMAL]:
				var a: PackedVector3Array = old_arrays[slot]; var b: PackedVector3Array = new_arrays[slot]
				for i in range(a.size()):
					if not a[i].is_equal_approx(b[i]):
						push_error("Batched cloth changed a vertex or normal from the baseline"); quit(1); return
		print("DUVET_HELD_HEM_US before=",before_us/48.0," after=",after_us/48.0)
		old_cloth.free()
	duvet.sample(0.0, 0.0, 0.0, 0.0, 0.0)
	if cloth.mesh != resource:
		push_error("Uncovered bed did not restore its authored mesh"); quit(1); return
	cloth.free()
	print("PASS exact cloth samples, topology, material, unchanged-frame reuse and rest restoration")
	quit(0)
