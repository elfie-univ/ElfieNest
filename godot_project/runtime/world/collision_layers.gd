extends RefCounted

# Technical access boundaries affect movement/navigation, never perception.
const WORLD_SOLIDS := 1
const MOVEMENT_BOUNDARY := 128
const PERCEPTION_ONLY := 256
const PERCEPTION_MASK := 0xffffffff ^ MOVEMENT_BOUNDARY
const NAVIGATION_MASK := WORLD_SOLIDS | MOVEMENT_BOUNDARY
