@tool
class_name ModularRoomDimensions
extends RefCounted

const CELL_PITCH: float = 5.6
const CLEAR_WIDTH: float = 5.5
const WALL_THICKNESS: float = 0.1
const WALL_HEIGHT: float = 3.0
const MAX_BED_COUNT: int = 32

const ACTIVITY_DEPTH: float = 3.7
const CORRIDOR_WIDTH: float = 3.0
const DORM_DEPTH: float = 3.9

const ACTIVITY_INNER_X: float = -CORRIDOR_WIDTH / 2.0
const ACTIVITY_OUTER_X: float = ACTIVITY_INNER_X - ACTIVITY_DEPTH
const ACTIVITY_CENTER_X: float = (ACTIVITY_INNER_X + ACTIVITY_OUTER_X) / 2.0

const DORM_INNER_X: float = CORRIDOR_WIDTH / 2.0
const DORM_OUTER_X: float = DORM_INNER_X + DORM_DEPTH
const DORM_CENTER_X: float = (DORM_INNER_X + DORM_OUTER_X) / 2.0

const EXTERIOR_COLOR := Color("#303943")
const CORRIDOR_COLOR := Color("#e1e3e0")
const CORRIDOR_WALL_COLOR := Color("#e9e3d8")
const DORM_WALL_COLOR := Color("#d3d5de")
const DORM_FLOOR_COLOR := Color("#a4a3a6")
const DORM_DOOR_COLOR := Color("#d8cdbb")
const DORM_RUG_COLOR := Color("#4d5968")
const DORM_RUG_TRIM_COLOR := Color("#d6d2c9")


static func room_count_for_beds(bed_count: int) -> int:
	var bounded_bed_count := clampi(bed_count, 1, MAX_BED_COUNT)
	return maxi(1, ceili(float(bounded_bed_count) / 4.0))


static func cell_center_z(index: int) -> float:
	return -(float(index) + 0.5) * CELL_PITCH
