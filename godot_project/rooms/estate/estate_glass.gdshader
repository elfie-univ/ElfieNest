shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_disabled, diffuse_lambert;

#include "estate_iridescence.gdshaderinc"

uniform vec4 source_albedo : source_color;
uniform float source_roughness = 0.05;
uniform float source_transmission = 1.0;
uniform float source_ior = 1.5;
uniform float source_clearcoat = 0.0;
uniform float source_coat_roughness = 0.0;
uniform float source_iridescence = 0.0;
uniform float source_film_ior = 1.3;
uniform float source_film_thickness = 400.0;
uniform vec4 source_emission : source_color;
uniform float source_thickness = 0.0;
uniform float source_attenuation_distance = 0.0;
uniform vec4 source_attenuation_color : source_color = vec4(1.0);
uniform sampler2D scene_color : hint_screen_texture, repeat_disable, filter_linear_mipmap;

vec3 to_linear(vec3 color) {
	return mix(color / 12.92, pow((color + 0.055) / 1.055, vec3(2.4)), step(vec3(0.04045), color));
}

vec3 to_srgb(vec3 color) {
	return mix(color * 12.92, 1.055 * pow(max(color, vec3(0.0)), vec3(1.0 / 2.4)) - 0.055, step(vec3(0.0031308), color));
}

vec3 scene_radiance(vec3 displayed) {
	// Compatibility copies a tone-mapped SDR screen. Undo this scene's ACES
	// and exposure before combining transmission with reflected radiance, so
	// the opaque scene is not exposed/tone-mapped twice through the pane.
	const mat3 rrt = mat3(vec3(0.59719, 0.35458, 0.04823) * 1.8, vec3(0.07600, 0.90834, 0.01566) * 1.8, vec3(0.02840, 0.13383, 0.83777) * 1.8);
	const mat3 odt = mat3(vec3(1.60475, -0.53108, -0.07367), vec3(-0.10208, 1.10813, -0.00605), vec3(-0.00327, -0.07276, 1.07602));
	const float a = 0.0245786;
	const float b = 0.000090537;
	const float c = 0.983729;
	const float d = 0.432951;
	const float e = 0.238081;
	const float white = (1.8 * (1.8 + a) - b) / (1.8 * (c * 1.8 + d) + e);
	vec3 value = clamp(to_linear(displayed) * white * inverse(odt), vec3(0.0), vec3(0.999));
	vec3 qa = vec3(1.0) - value * c;
	vec3 qb = value * d - vec3(a);
	vec3 qc = value * e + vec3(b);
	vec3 linear = (qb + sqrt(qb * qb + 4.0 * qa * qc)) / (2.0 * qa);
	return max(linear * inverse(rrt) / 0.88, vec3(0.0));
}

void fragment() {
	NORMAL = normalize(NORMAL);
	if (dot(NORMAL, VIEW) < 0.0) {
		NORMAL = -NORMAL;
	}
	float ratio = (source_ior - 1.0) / (source_ior + 1.0);
	float f0 = ratio * ratio;
	float ndotv = clamp(abs(dot(NORMAL, VIEW)), 0.0, 1.0);
	float grazing = min(pow(1.0 - ndotv, 5.0), 0.9999);
	vec3 fresnel = vec3(f0 + (1.0 - f0) * grazing);
	vec3 film = evalIridescence(1.0, source_film_ior, ndotv, source_film_thickness, vec3(f0));
	fresnel = mix(fresnel, film, source_iridescence);
	vec3 effective_f0 = clamp((fresnel - vec3(grazing)) / (1.0 - grazing), vec3(0.0), vec3(1.0));
	vec3 ray = refract(-VIEW, NORMAL, 1.0 / source_ior);
	vec3 exit_point = VERTEX + ray * source_thickness;
	vec4 projected = PROJECTION_MATRIX * vec4(exit_point, 1.0);
	vec2 refracted_uv = projected.xy / projected.w * 0.5 + 0.5;
	vec3 behind = scene_radiance(textureLod(scene_color, clamp(refracted_uv, vec2(0.0), vec2(1.0)), source_roughness * 8.0).rgb);
	vec3 attenuation = vec3(1.0);
	if (source_attenuation_distance > 0.0) {
		attenuation = pow(max(source_attenuation_color.rgb, vec3(0.0001)), vec3(source_thickness / source_attenuation_distance));
	}
	vec3 transmitted = behind * to_linear(source_albedo.rgb) * attenuation * source_transmission * (vec3(1.0) - fresnel);
	// Screen-reading materials are transparent-queue draws; their output
	// already contains the transmitted scene, independent of coverage alpha.
	ALPHA = 1.0;
	// Metallic=1 exposes a colored Fresnel F0 in Godot's native GGX/IBL;
	// this is a dielectric coating response, not an edit to source RGB.
	ALBEDO = to_srgb(effective_f0);
	METALLIC = 1.0;
	EMISSION = to_srgb(transmitted + to_linear(source_emission.rgb) + to_linear(source_albedo.rgb) * (1.0 - source_transmission) * (0.72 / PI));
	SPECULAR = abs(ratio) / 0.4;
	ROUGHNESS = source_roughness;
	CLEARCOAT = source_clearcoat;
	float coat = max(source_coat_roughness, 0.0525);
	CLEARCOAT_ROUGHNESS = clamp((coat * coat - 0.001) / 0.099, 0.0, 1.0);
}
