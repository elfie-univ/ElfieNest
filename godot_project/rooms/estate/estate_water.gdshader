shader_type spatial;
render_mode cull_disabled, diffuse_lambert, specular_schlick_ggx;

uniform vec4 source_albedo : source_color;
uniform float source_roughness = 0.22;
uniform float source_metallic = 0.02;
uniform float source_specular = 0.5;
uniform float source_clearcoat = 0.0;
uniform float source_coat_roughness = 0.0;
uniform bool is_spillway = false;
varying vec3 water_position;

void vertex() {
	// Coordinates only: no vertex displacement or changes to physical shape.
	water_position = VERTEX;
}

void fragment() {
	float speed = is_spillway ? 1.1 : 0.22;
	float phase = TIME * speed;
	vec2 slope = vec2(
		cos(water_position.x * 2.1 + water_position.z * 1.3 - phase),
		sin(water_position.z * 2.7 - water_position.x * 0.7 + phase * 0.71)
	) * 0.025;
	vec3 ripple = mat3(VIEW_MATRIX * MODEL_MATRIX) * vec3(slope.x, 0.0, slope.y);
	NORMAL = normalize(NORMAL + ripple);
	if (dot(NORMAL, VIEW) < 0.0) {
		NORMAL = -NORMAL;
	}
	ALBEDO = source_albedo.rgb;
	METALLIC = source_metallic;
	SPECULAR = source_specular;
	ROUGHNESS = source_roughness;
	CLEARCOAT = source_clearcoat;
	float coat = max(source_coat_roughness, 0.0525);
	CLEARCOAT_ROUGHNESS = clamp((coat * coat - 0.001) / 0.099, 0.0, 1.0);
}
