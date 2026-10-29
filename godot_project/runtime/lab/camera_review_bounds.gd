extends RefCounted
## Explicit local candidate only. No input hooks or product defaults are installed.

const YAW_RANGE_DEGREES := 30.0
const PITCH_RANGE_DEGREES := 10.0
const MIN_FOV := 34.0
const MAX_FOV := 60.0

var _nest: ModularNest
var _camera: Camera3D
var _baseline_yaw: float
var _baseline_pitch: float
var _baseline_transform: Transform3D
var _baseline_fov: float


func _init(nest: ModularNest, camera: Camera3D) -> void:
	_nest = nest
	_camera = camera
	_baseline_yaw = float(nest.get("_camera_yaw"))
	_baseline_pitch = float(nest.get("_camera_pitch"))
	_baseline_transform = camera.global_transform
	_baseline_fov = camera.fov


func set_candidate(yaw_degrees: float, pitch_degrees: float, fov: float) -> void:
	var yaw := _baseline_yaw + deg_to_rad(clampf(yaw_degrees, -YAW_RANGE_DEGREES, YAW_RANGE_DEGREES))
	var pitch := _baseline_pitch + deg_to_rad(clampf(pitch_degrees, -PITCH_RANGE_DEGREES, PITCH_RANGE_DEGREES))
	pitch = clampf(pitch, ModularNest.CAMERA_MIN_PITCH, ModularNest.CAMERA_MAX_PITCH)
	_nest.set("_camera_yaw", yaw)
	_nest.set("_camera_pitch", pitch)
	_camera.fov = clampf(fov, MIN_FOV, MAX_FOV)
	_nest._apply_camera_transform(_camera)


func clamp_current() -> void:
	# Preserve the exact original preset on reset, including its authored pitch.
	if _camera.global_transform.is_equal_approx(_baseline_transform) and is_equal_approx(_camera.fov, _baseline_fov):
		return
	var yaw := angle_difference(_baseline_yaw, float(_nest.get("_camera_yaw")))
	var pitch := float(_nest.get("_camera_pitch")) - _baseline_pitch
	set_candidate(rad_to_deg(yaw), rad_to_deg(pitch), _camera.fov)


func reset() -> void:
	_nest.reset_observation_camera()


func limits() -> Dictionary:
	return {
		"scope": "explicit developer sample only; user approval pending",
		"yaw_relative_degrees": [-YAW_RANGE_DEGREES, YAW_RANGE_DEGREES],
		"pitch_absolute_degrees": [
			rad_to_deg(maxf(_baseline_pitch - deg_to_rad(PITCH_RANGE_DEGREES), ModularNest.CAMERA_MIN_PITCH)),
			rad_to_deg(minf(_baseline_pitch + deg_to_rad(PITCH_RANGE_DEGREES), ModularNest.CAMERA_MAX_PITCH)),
		],
		"fov_degrees": [MIN_FOV, MAX_FOV],
		"reset": "original M01 optical sample camera transform and FOV",
	}
