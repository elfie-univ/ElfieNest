shader_type spatial;
render_mode unshaded, cull_disabled, shadows_disabled;

#include "res://nest/rendering/estate_night_sky.gdshaderinc"

uniform bool dome = true;
uniform vec3 projection_origin;
varying vec3 projection_ray;

void vertex() {
	projection_ray = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz - projection_origin;
}

void fragment() {
	// The dome faces inward and the original cylindrical wall faces outward.
	// Draw only the inner faces so the near wall does not hide an exterior view.
	if (FRONT_FACING != dome) {
		discard;
	}
	// Compatibility's unshaded pass outputs ALBEDO. Include the star and
	// galaxy light in that color so the roof needs no scene lights.
	ALBEDO = night_sky(normalize(projection_ray));
}
