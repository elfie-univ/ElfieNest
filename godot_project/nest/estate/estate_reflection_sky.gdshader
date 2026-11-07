shader_type sky;

// Retain the reviewed reflection input independently of the visible night sky.
// Compatibility's sky pass decodes these canvas sRGB values itself.
uniform vec4 environment_color = vec4(0.72, 0.78, 0.81, 1.0);
uniform float night_amount : hint_range(0.0, 1.0) = 0.0;

float star_hash(vec2 cell) {
	return fract(sin(dot(cell, vec2(127.1, 311.7))) * 43758.5453);
}

float sky_noise(vec2 point) {
	vec2 cell = floor(point);
	vec2 blend = fract(point);
	blend = blend * blend * (3.0 - 2.0 * blend);
	return mix(mix(star_hash(cell), star_hash(cell + vec2(1.0, 0.0)), blend.x),
		mix(star_hash(cell + vec2(0.0, 1.0)), star_hash(cell + vec2(1.0)), blend.x), blend.y);
}

float sky_dust(vec2 point) {
	float value = 0.0;
	float weight = 0.5;
	for (int octave = 0; octave < 4; octave++) {
		value += sky_noise(point) * weight;
		point = mat2(vec2(1.6, 1.2), vec2(-1.2, 1.6)) * point + 17.3;
		weight *= 0.5;
	}
	return value;
}

vec3 milky_way(vec3 direction) {
	vec3 normal = normalize(vec3(0.62, 0.59, -0.52));
	vec3 tangent = normalize(cross(normal, vec3(0.0, 1.0, 0.0)));
	vec3 along_plane = cross(normal, tangent);
	float distance = dot(direction, normal);
	float along = atan(dot(direction, tangent), dot(direction, along_plane));
	vec2 dust_uv = vec2(along * 9.0, distance * 30.0);
	float clouds = sky_dust(dust_uv);
	float band = exp(-pow(distance / 0.085, 2.0));
	float halo = exp(-pow(distance / 0.19, 2.0));
	float lane_center = (sky_noise(vec2(along * 7.0, 3.1)) - 0.5) * 0.035;
	float lane = exp(-pow((distance - lane_center) / 0.021, 2.0));
	float dust = lane * (0.35 + 0.65 * sky_dust(dust_uv * 1.8 + 31.0));
	vec3 glow = vec3(0.20, 0.22, 0.34) * band * (0.25 + clouds * 0.95) * (1.0 - dust * 0.82);
	glow += vec3(0.025, 0.035, 0.065) * halo * clouds;
	// Fine distant stars gather in the galactic band, between brighter stars.
	vec2 grid = vec2(atan(direction.z, direction.x) / TAU + 0.5,
		asin(clamp(direction.y, -1.0, 1.0)) / PI + 0.5) * vec2(384.0, 192.0);
	vec2 cell = floor(grid);
	float seed = star_hash(cell + 91.3);
	vec2 center = vec2(star_hash(cell + 7.1), star_hash(cell + 39.2)) * 0.76 + 0.12;
	float pixel = max(length(fwidth(grid)), 0.008);
	float core = 1.0 - smoothstep(0.012, 0.012 + pixel * 0.55, length(fract(grid) - center));
	glow += vec3(0.70, 0.79, 1.0) * core * step(0.975 - band * 0.14, seed) * (0.12 + band * 0.25);
	return glow * smoothstep(0.01, 0.16, direction.y);
}

vec3 night_sky(vec3 direction) {
	float altitude = max(direction.y, 0.0);
	float horizon = pow(1.0 - altitude, 4.0);
	vec3 color = mix(vec3(0.045, 0.075, 0.15), vec3(0.16, 0.205, 0.29), horizon);
	color += milky_way(direction);
	// Fixed celestial directions: stars stay in place when the camera moves.
	vec2 grid = vec2(atan(direction.z, direction.x) / TAU + 0.5,
		asin(clamp(direction.y, -1.0, 1.0)) / PI + 0.5) * vec2(128.0, 64.0);
	vec2 cell = floor(grid);
	float seed = star_hash(cell);
	vec2 center = vec2(star_hash(cell + vec2(19.7, 5.3)),
		star_hash(cell + vec2(4.1, 37.9))) * 0.72 + 0.14;
	vec2 offset = fract(grid) - center;
	float pixel = max(length(fwidth(grid)), 0.008);
	float radius = mix(0.018, 0.038, star_hash(cell + 7.3));
	float core = 1.0 - smoothstep(radius, radius + pixel * 0.65, length(offset));
	// Only a small fraction of the scattered stars carry a diamond glint.
	float diamond = pow(max(1.0 - (abs(offset.x) + abs(offset.y)) / 0.18, 0.0), 2.0);
	float glint = seed > 0.985 ? diamond * 0.85 : 0.0;
	float stars = (core + glint) * step(0.86, seed) * smoothstep(0.015, 0.14, direction.y);
	vec3 tint = mix(vec3(0.73, 0.83, 1.0), vec3(1.0, 0.94, 0.82), star_hash(cell + 43.8));
	color += tint * stars * mix(0.45, 1.15, star_hash(cell + 13.4));
	return color;
}

void sky() {
	COLOR = environment_color.rgb;
	// The visible night sky is independent of the approved room illumination
	// and reflection cubemap. Daytime keeps its existing sky geometry.
	if (night_amount > 0.5 && !AT_CUBEMAP_PASS) {
		COLOR = night_sky(normalize(EYEDIR));
	}
}
