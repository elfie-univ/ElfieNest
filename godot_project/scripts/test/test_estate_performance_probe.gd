extends SceneTree

func _initialize() -> void:
	create_timer(10.0).timeout.connect(func(): quit(1))
	var probe=load("res://runtime/lab/estate_performance_probe.gd")
	var data: Array[float]=[7,1,3,2,10]
	assert(probe.percentile(data,.5)==3)
	assert(probe.percentile(data,.95)==10)
	assert(data==[7.0,1.0,3.0,2.0,10.0])
	var sun=DirectionalLight3D.new()
	sun.shadow_enabled=true;sun.light_energy=2.0;sun.light_cull_mask=13;sun.shadow_caster_mask=23
	var daylight=preload("res://rooms/estate/estate_daylight.gd")
	daylight._apply_web_shadow_budget(sun)
	assert(sun.directional_shadow_max_distance==30.0)
	assert(is_equal_approx(sun.directional_shadow_fade_start,.7))
	assert(sun.directional_shadow_mode==DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS)
	assert(sun.shadow_enabled and sun.light_energy==2.0 and sun.light_cull_mask==13 and sun.shadow_caster_mask==23)
	sun.directional_shadow_max_distance=12.0;sun.directional_shadow_fade_start=.5;sun.directional_shadow_mode=DirectionalLight3D.SHADOW_ORTHOGONAL
	daylight._apply_web_shadow_budget(sun)
	assert(sun.directional_shadow_max_distance==12.0 and sun.directional_shadow_fade_start==.5 and sun.directional_shadow_mode==DirectionalLight3D.SHADOW_ORTHOGONAL)
	sun.free()
	var source=ArrayMesh.new()
	var arrays=[]
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX]=PackedVector3Array([Vector3.ZERO,Vector3.RIGHT,Vector3.UP,Vector3(1,1,0)])
	arrays[Mesh.ARRAY_INDEX]=PackedInt32Array([0,1,2,1,3,2])
	source.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays,[],{10.0:PackedInt32Array([0,1,2])})
	source.shadow_mesh=source.duplicate() as ArrayMesh
	source.set_meta("full_detail_canopy",true)
	var estate=preload("res://rooms/estate/estate_complete_final.gd").new()
	var result=estate._full_detail_canopy(source) as ArrayMesh
	if result.shadow_mesh!=source.shadow_mesh:
		push_error("Canopy conversion dropped the imported shadow mesh")
		estate.free();quit(1);return
	var before: Dictionary=source.get("_surfaces")[0].duplicate()
	before.erase("lods")
	var after: Dictionary=result.get("_surfaces")[0].duplicate()
	after.erase("lods")
	if after!=before:
		push_error("Visible canopy buffers changed")
		estate.free();quit(1);return
	assert(not source.get("_surfaces")[0]["lods"].is_empty(),"Source LODs must remain untouched")
	assert(estate._full_detail_canopy(source)==result,"Keep mesh caching")
	estate.free()
	var transforms=PackedFloat32Array()
	transforms.resize(256*12)
	for i in range(256):
		transforms[i*12]=1;transforms[i*12+5]=1;transforms[i*12+10]=1
		transforms[i*12+3]=float(i%2)*14.0
	var batches=CompleteEstateFinal._spatial_batches(transforms)
	assert(batches.size()==2,"Locality must not add render batches")
	var seen={}
	var total_width=0.0
	for batch: Dictionary in batches:
		assert(batch.source_indices.size()==128)
		var low=INF;var high=-INF
		for i in range(batch.source_indices.size()):
			var source_index=int(batch.source_indices[i])
			assert(not seen.has(source_index));seen[source_index]=true
			for component in range(12):
				assert(batch.buffer[i*12+component]==transforms[source_index*12+component],"Every transform component must stay exact")
			low=minf(low,batch.buffer[i*12+3]);high=maxf(high,batch.buffer[i*12+3])
		total_width+=high-low
	if seen.size()!=256 or total_width>0.01:
		push_error("Spatial batches still mix distant instances: width="+str(total_width))
		quit(1);return
	print("PASS performance percentiles, exact visible buffers, shadow mesh and source/cache preservation")
	quit()
