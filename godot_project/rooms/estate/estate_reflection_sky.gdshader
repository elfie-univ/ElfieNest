shader_type sky;

// Reflection-only counterpart of the approved viewer's authored environment.
// The visible sky/cloud meshes are not replaced. Work in the same canvas sRGB
// gradient. Compatibility's sky pass performs the sRGB decode itself; decoding
// here again darkens the reflection and removes the intended soft sheen.
vec3 reflection_gradient(float y) {
	if (y < 0.42) {
		return mix(vec3(230.0, 228.0, 240.0), vec3(156.0, 170.0, 181.0), y / 0.42) / 255.0;
	}
	if (y < 0.55) {
		return mix(vec3(156.0, 170.0, 181.0), vec3(83.0, 93.0, 102.0), (y - 0.42) / 0.13) / 255.0;
	}
	return mix(vec3(83.0, 93.0, 102.0), vec3(117.0, 101.0, 85.0), (y - 0.55) / 0.45) / 255.0;
}

vec3 soft_reflection(vec3 base, vec2 uv, vec2 center, vec2 radius, vec3 tint) {
	float r = length((uv - center) / radius);
	float alpha = r < 0.55 ? mix(0.9, 0.4, r / 0.55) : mix(0.4, 0.0, clamp((r - 0.55) / 0.45, 0.0, 1.0));
	return mix(base, tint / 255.0, alpha);
}

void sky() {
	vec2 uv = vec2(atan(EYEDIR.z, EYEDIR.x) / TAU + 0.5, acos(clamp(EYEDIR.y, -1.0, 1.0)) / PI);
	vec3 color = reflection_gradient(uv.y);
	color = soft_reflection(color, uv, vec2(45.0 / 512.0, 0.5), vec2(130.0 / 512.0, 180.0 / 256.0), vec3(90.0, 215.0, 242.0));
	color = soft_reflection(color, uv, vec2(250.0 / 512.0, 0.5), vec2(110.0 / 512.0, 170.0 / 256.0), vec3(209.0, 160.0, 245.0));
	color = soft_reflection(color, uv, vec2(450.0 / 512.0, 0.5), vec2(120.0 / 512.0, 170.0 / 256.0), vec3(255.0, 213.0, 162.0));
	COLOR = color;
}
