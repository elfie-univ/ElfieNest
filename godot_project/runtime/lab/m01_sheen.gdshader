shader_type spatial;
render_mode cull_disabled, diffuse_lambert, specular_schlick_ggx;
uniform vec4 source_albedo : source_color;
uniform float source_roughness = 0.88;
uniform sampler2D source_normal : hint_normal, filter_linear_mipmap, repeat_enable;
uniform float source_normal_scale = 0.2;
uniform vec3 sheen_color = vec3(1.0);
uniform float sheen_roughness = 0.8;
uniform float sheen_amount = 1.0;
uniform bool use_authored_reflection = false;

// Integrated Charlie lobe used by the reference physical material to reserve
// energy for the cloth layer instead of adding it on top of the full base BRDF.
float sheen_albedo(float cosine) {
	float r2 = sheen_roughness * sheen_roughness;
	float inverse_r = 1.0 / (sheen_roughness + 0.1);
	float a = -1.9362 + 1.0678 * sheen_roughness + 0.4573 * r2 - 0.8469 * inverse_r;
	float b = -0.6014 + 0.5538 * sheen_roughness - 0.4670 * r2 - 0.1255 * inverse_r;
	return clamp(exp(a * cosine + b), 0.0, 1.0);
}

vec3 to_linear(vec3 value) {
	return mix(value / 12.92, pow((value + 0.055) / 1.055, vec3(2.4)), step(vec3(0.04045), value));
}

vec3 to_srgb(vec3 value) {
	return mix(value * 12.92, 1.055 * pow(max(value, vec3(0.0)), vec3(1.0 / 2.4)) - 0.055, step(vec3(0.0031308), value));
}

// Charlie distribution / Neubelt visibility as specified by KHR_materials_sheen.
// The source normal texture and albedo remain the imported, unmodified inputs.
void fragment() {
	if (!use_authored_reflection) {
		RADIANCE = vec4(0.0, 0.0, 0.0, 1.0);
	}
	NORMAL = normalize(NORMAL);
	ALBEDO = source_albedo.rgb;
	ROUGHNESS = source_roughness;
	vec3 mapped = texture(source_normal, UV).rgb * 2.0 - 1.0;
	// Imported normal maps can store only RG. Reconstruct Z before applying
	// the source's XY normal scale, as in the reference physical material.
	mapped.z = sqrt(max(1.0 - dot(mapped.xy, mapped.xy), 0.0));
	mapped.xy *= source_normal_scale;
	NORMAL = normalize(TANGENT * mapped.x + BINORMAL * mapped.y + NORMAL * mapped.z);
	if (dot(NORMAL, VIEW) < 0.0) {
		NORMAL = -NORMAL;
	}
	vec3 world_normal = normalize(mat3(INV_VIEW_MATRIX) * NORMAL);
	vec3 hemisphere = mix(to_linear(vec3(0.352941, 0.407843, 0.364706)), to_linear(vec3(0.843137, 0.921569, 1.0)), world_normal.y * 0.5 + 0.5) * (0.72 / PI);
	float cloth_albedo = sheen_albedo(max(dot(NORMAL, VIEW), 0.0));
	float sheen_max = max(sheen_color.r, max(sheen_color.g, sheen_color.b));
	IRRADIANCE = vec4(hemisphere * 0.96 * (1.0 - sheen_amount * sheen_max * cloth_albedo), 1.0);
	// GLES3 decodes EMISSION after fragment(); do not decode the original
	// albedo or LIGHT_COLOR a second time inside light().
	EMISSION = to_srgb(hemisphere * sheen_color * cloth_albedo * sheen_amount);
}

void light() {
	float nl = max(dot(NORMAL, LIGHT), 0.0);
	float nv = max(dot(NORMAL, VIEW), 0.0001);
	vec3 half_vector = normalize(LIGHT + VIEW);
	float nh = max(dot(NORMAL, half_vector), 0.0);
	float vh = max(dot(VIEW, half_vector), 0.0);
	float alpha = max(source_roughness * source_roughness, 0.002);
	float alpha2 = alpha * alpha;
	float denominator = nh * nh * (alpha2 - 1.0) + 1.0;
	float distribution = alpha2 / max(PI * denominator * denominator, 0.0001);
	float gv = nl * sqrt(nv * nv * (1.0 - alpha2) + alpha2);
	float gl = nv * sqrt(nl * nl * (1.0 - alpha2) + alpha2);
	float visibility = 0.5 / max(gv + gl, 0.0001);
	float fresnel = 0.04 + 0.96 * pow(1.0 - vh, 5.0);
	float inverse_alpha = 1.0 / max(sheen_roughness * sheen_roughness, 0.002);
	float charlie = (2.0 + inverse_alpha) * pow(max(1.0 - nh * nh, 0.0078125), inverse_alpha * 0.5) / (2.0 * PI);
	float neubelt = clamp(1.0 / max(4.0 * (nl + nv - nl * nv), 0.0001), 0.0, 1.0);
	vec3 illumination = ATTENUATION * LIGHT_COLOR * nl;
	float sheen_max = max(sheen_color.r, max(sheen_color.g, sheen_color.b));
	float base_energy = 1.0 - sheen_amount * sheen_max * max(sheen_albedo(nv), sheen_albedo(nl));
	DIFFUSE_LIGHT += illumination * base_energy * (1.0 - fresnel) / PI;
	SPECULAR_LIGHT += illumination * (base_energy * distribution * visibility * fresnel + sheen_amount * sheen_color * charlie * neubelt);
}
