extends SceneTree
const TIMING := preload("res://runtime/lab/estate_platform_cycle.gd")
class CameraNest extends ModularNest:
	func _ready() -> void: pass
func _initialize() -> void:call_deferred("run")
func run() -> void:
	var nest := CameraNest.new()
	var hud: Node = load("res://ui/observation_hud.tscn").instantiate()
	hud.name="ObservationHUD"
	nest.add_child(hud)
	root.add_child(nest)
	var review: Node3D = load("res://runtime/lab/estate_event_review.gd").new()
	review.set("camera_owner",nest)
	root.add_child(review)
	review.set_process(false)
	var cycle := review.get("platform_cycle") as Node3D
	var body := cycle.get_node("LocalPlatformBody") as Node3D
	var steps: MeshInstance3D
	var t1: MeshInstance3D
	var interior_band: MeshInstance3D
	for mesh: MeshInstance3D in review.get("review_geometry").find_children("*","MeshInstance3D",true,false):
		var e := mesh.get_meta("extras",{}) as Dictionary
		if e.get("assembly")=="roof01_steps":steps=mesh
		if str(mesh.name).begins_with("Roof lighting upper perimeter cove flush diffuser"):interior_band=mesh
		if str(mesh.name)=="Central skylight soft luminous inset":t1=mesh
	assert(steps!=null and t1!=null)
	var target := (steps.global_transform*steps.get_aabb()).get_center()
	var direction := target-body.global_position
	direction.y=0
	if not _require(body.global_basis.z.normalized().dot(direction.normalized())>0.99,"Actor faces the building stairwell rather than the two platform steps"):return
	for point: Vector3 in t1.mesh.get_faces():
		var world := t1.to_global(point)
		var radius := Vector2(world.x,world.z).length()
		if not _require(radius>=3.60 and radius<=3.92,"T1 is still over the glass instead of inside the frame footprint"):return
	var light: Node = review.get("arrival_lighting")
	if not _require(light!=null,"Missing coordinated rooftop fixture lighting"):return
	if not _require(light.get_node_or_null("SaucerSeamBand")==null,"Rejected exterior band still exists"):return
	if not _require(interior_band!=null,"Original interior upper cove diffuser is missing"):return
	var band_bounds := interior_band.global_transform*interior_band.get_aabb()
	if not _require(band_bounds.get_center().y>11.95 and band_bounds.get_center().y<12.1 and band_bounds.size.x<10.8,"Interior band moved onto the outside shell"):return
	var minimum := INF
	var maximum := 0.0
	for point: Vector3 in interior_band.mesh.get_faces():
		var world := interior_band.to_global(point)
		var radius := Vector2(world.x,world.z).length()
		minimum=minf(minimum,radius)
		maximum=maxf(maximum,radius)
	if not _require(maximum-minimum>=0.16 and minimum>5.1 and maximum<5.4,"Original interior ring did not gain a bounded wider diffuser"):return
	var group_starts := []
	for group: String in ["top_1","top_2","top_3"]:
		var found := false
		for binding: Dictionary in light.get("bindings"):
			if binding["group"]==group:
				group_starts.append(binding["delay"])
				found=true
				break
		if not _require(found,"Missing roof sequence group: "+group):return
	for i in range(1,group_starts.size()):
		if not _require(float(group_starts[i])>float(group_starts[i-1]),"Rooftop lights do not cascade inside-out then downward"):return
	cycle.call("sample",TIMING.PREPARE_SECONDS+3.35)
	var upper := body.global_position.y
	var early := float(cycle.get("body_presence"))
	cycle.call("sample",TIMING.PREPARE_SECONDS+4.8)
	if not _require(body.global_position.y<upper and float(cycle.get("body_presence"))>early,"Actor does not slowly descend and materialize"):return
	var beam := review.get("effects").get_node("ArrivalEffect/ArrivalBeam") as MeshInstance3D
	if not _require(beam.visible and beam.material_override is ShaderMaterial,"Transparent rotating cylinder was removed"):return
	if not _require(cycle.get("descent_rings").size()==3,"Descending colored rings were lost"):return
	cycle.call("sample",TIMING.PREPARE_SECONDS+5.8)
	var landing := cycle.get_node_or_null("LandingWave") as MeshInstance3D
	var motes := cycle.get_node_or_null("ArrivalMotes") as MultiMeshInstance3D
	if not _require(landing!=null and landing.visible and motes!=null and motes.visible,"Missing landing wave or convergence particles"):return
	if not _require(absf(body.global_position.y-float(cycle.get("standing_y")))<0.03,"Actor never lands on the actual platform"):return
	cycle.call("cancel")
	if not _require(not body.visible and not beam.visible and not landing.visible and not motes.visible,"Cancel retained arrival effects"):return
	review.free()
	nest.free()
	print("PASS T1 frame placement, original interior cove band without exterior additions, clockwise cascading roof groups, platform-step facing, gradual descent/reveal, seven effects and cancellation")
	quit(0)
func _require(ok: bool,message: String) -> bool:
	if not ok:push_error(message);quit(1)
	return ok
