extends RefCounted
## A continuous light inlay on an owned copy of the actual ceramic surface.
const SHADER := preload("res://runtime/lab/estate_arrival_inlay.gdshader")

static func install(mesh: MeshInstance3D) -> ShaderMaterial:
	var source := mesh.mesh
	var bounds := mesh.global_transform*source.get_aabb()
	var center := bounds.get_center()
	var across := Vector3(-center.z,0,center.x).normalized()
	var minima: Array[float] = []
	var maxima: Array[float] = []
	minima.resize(64); minima.fill(INF)
	maxima.resize(64); maxima.fill(-INF)
	var ceramic := source.surface_get_arrays(0)
	for vertex: Vector3 in ceramic[Mesh.ARRAY_VERTEX]:
		var world := mesh.to_global(vertex)
		var row := clampi(int((world.y-bounds.position.y)/bounds.size.y*63.0),0,63)
		var x := (world-center).dot(across)
		minima[row]=minf(minima[row],x)
		maxima[row]=maxf(maxima[row],x)
	for row in range(64):
		if is_finite(minima[row]): continue
		for distance in range(1,64):
			var near := maxi(0,row-distance)
			if not is_finite(minima[near]): near=mini(63,row+distance)
			if is_finite(minima[near]):
				minima[row]=minima[near]; maxima[row]=maxima[near]
				break
	var material := ShaderMaterial.new()
	material.shader=SHADER
	var base := source.surface_get_material(0) as BaseMaterial3D
	material.set_shader_parameter("ceramic",base.albedo_color)
	var owned := ArrayMesh.new()
	for surface in range(source.get_surface_count()):
		var arrays := source.surface_get_arrays(surface).duplicate(true)
		if surface==0:
			var uv := PackedVector2Array()
			for vertex: Vector3 in arrays[Mesh.ARRAY_VERTEX]:
				var world := mesh.to_global(vertex)
				var h := clampf((world.y-bounds.position.y)/bounds.size.y,0.0,1.0)
				var row := clampi(int(h*63.0),0,63)
				var half_width := maxf(0.025,(maxima[row]-minima[row])*0.5)
				uv.append(Vector2(((world-center).dot(across)-(minima[row]+maxima[row])*0.5)/half_width,h))
			arrays[Mesh.ARRAY_TEX_UV2]=uv
		owned.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
		owned.surface_set_material(surface,material if surface==0 else source.surface_get_material(surface))
	mesh.mesh=owned
	mesh.set_surface_override_material(0,material)
	return material
