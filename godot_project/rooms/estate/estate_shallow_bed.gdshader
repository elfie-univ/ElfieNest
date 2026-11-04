shader_type spatial;
render_mode cull_disabled, diffuse_lambert;

uniform vec4 source_albedo : source_color;
uniform float source_roughness = 0.85;
varying vec3 bed_world;
varying vec3 bed_normal;

vec2 stone_hash(vec2 cell) {
	return fract(sin(vec2(dot(cell, vec2(127.1, 311.7)), dot(cell, vec2(269.5, 183.3)))) * 43758.5453);
}

void vertex() {
	bed_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	bed_normal = normalize(MODEL_NORMAL_MATRIX * NORMAL);
}

void fragment() {
	vec2 position = bed_world.xz * 11.0;
	vec2 cell = floor(position);
	vec2 local = fract(position);
	float distance_to_stone = 2.0;
	float tone = 0.0;
	for (int x = -1; x <= 1; x++) {
		for (int y = -1; y <= 1; y++) {
			vec2 offset = vec2(float(x), float(y));
			vec2 random = stone_hash(cell + offset);
			float distance = length((offset + 0.22 + random * 0.56 - local) * vec2(1.0, 1.22));
			if (distance < distance_to_stone) { distance_to_stone = distance; tone = random.x; }
		}
	}
	float stone = 1.0 - smoothstep(0.34, 0.43, distance_to_stone);
	float top = smoothstep(0.7, 0.95, abs(bed_normal.y));
	vec3 pebble = mix(vec3(0.24, 0.22, 0.18), vec3(0.71, 0.66, 0.53), tone);
	ALBEDO = mix(source_albedo.rgb, mix(source_albedo.rgb * 0.7, pebble, stone), top);
	ROUGHNESS = source_roughness;
}
