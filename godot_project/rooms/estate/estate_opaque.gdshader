shader_type spatial;
render_mode cull_disabled, diffuse_lambert, specular_schlick_ggx;

uniform vec4 source_albedo : source_color;
uniform float source_roughness = 0.5;
uniform float source_metallic = 0.0;
uniform float source_specular = 0.5;
uniform float source_clearcoat = 0.0;
uniform float source_coat_roughness = 0.0;
uniform bool use_linear_vertex_color = false;
uniform bool use_authored_reflection = false;

vec3 to_linear(vec3 color) {
	return mix(color / 12.92, pow((color + 0.055) / 1.055, vec3(2.4)), step(vec3(0.04045), color));
}

vec3 to_srgb(vec3 color) {
	return mix(color * 12.92, 1.055 * pow(max(color, vec3(0.0)), vec3(1.0 / 2.4)) - 0.055, step(vec3(0.0031308), color));
}

void fragment() {
	// The reference binds its studio environment only to opt-in finishes.
	// Applying it to every interior surface adds an unauthored blue sheen.
	if (!use_authored_reflection) {
		RADIANCE = vec4(0.0, 0.0, 0.0, 1.0);
	}
	// A two-sided surface must shade the visible side. A determinant-only
	// correction can turn interior ceilings toward the sky after import.
	NORMAL = normalize(NORMAL);
	if (dot(NORMAL, VIEW) < 0.0) {
		NORMAL = -NORMAL;
	}
	vec3 world_normal = normalize(mat3(INV_VIEW_MATRIX) * NORMAL);
	IRRADIANCE = vec4(mix(to_linear(vec3(0.352941, 0.407843, 0.364706)), to_linear(vec3(0.843137, 0.921569, 1.0)), world_normal.y * 0.5 + 0.5) * (0.72 / PI), 1.0);
	vec3 gradient = max(abs(dFdx(NORMAL)), abs(dFdy(NORMAL)));
	float geometry_roughness = max(gradient.x, max(gradient.y, gradient.z));
	ALBEDO = source_albedo.rgb;
	if (use_linear_vertex_color) {
		// glTF COLOR_0 is linear. Compatibility decodes ALBEDO after
		// fragment(), so encode the linear product once at that boundary.
		ALBEDO = to_srgb(to_linear(source_albedo.rgb) * COLOR.rgb);
	}
	METALLIC = source_metallic;
	SPECULAR = source_specular;
	// Match the reference's specular anti-aliasing without changing the
	// authored roughness, RGB, mesh detail or textures.
	ROUGHNESS = min(max(source_roughness, 0.0525) + geometry_roughness, 1.0);
	CLEARCOAT = source_clearcoat;
	float coat = min(max(source_coat_roughness, 0.0525) + geometry_roughness, 1.0);
	CLEARCOAT_ROUGHNESS = clamp((coat * coat - 0.001) / 0.099, 0.0, 1.0);
}
