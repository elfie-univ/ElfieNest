shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_disabled, diffuse_lambert;

uniform vec4 source_albedo : source_color;
uniform float source_roughness = 0.13;
uniform float source_metallic = 0.0;
uniform float source_specular = 0.5;
uniform bool is_ripple = false;
uniform bool source_unshaded = false;
uniform bool use_source_texture = false;
uniform sampler2D source_texture : source_color, filter_linear_mipmap, repeat_enable;
uniform vec3 accent_color = vec3(0.0);
uniform float accent_strength = 0.0;
varying vec3 water_position;

void vertex() {
	water_position = VERTEX;
}

void fragment() {
	// Animate highlights and coverage within the authored jet/ring geometry.
	// Hidden authority scenes submit no water draws; no CPU clock is needed.
	float coordinate = is_ripple ? length(water_position.xy) * 18.0 : water_position.y * 24.0;
	float phase = coordinate - TIME * (is_ripple ? 0.8 : -2.6);
	float wave = sin(phase);
	vec4 tint = source_albedo;
	if (use_source_texture) {
		tint *= texture(source_texture, UV + vec2(0.0, TIME * 0.025));
	}
	ALBEDO = source_unshaded ? vec3(0.0) : tint.rgb;
	EMISSION = (source_unshaded ? tint.rgb : vec3(0.0)) + accent_color * accent_strength;
	ALPHA = tint.a * (0.94 + wave * 0.06);
	// The authored rings are faint transparent water. Only their night pulse
	// gains coverage, so the illuminated ring remains readable without new mesh.
	if (is_ripple) {
		ALPHA = clamp(ALPHA + accent_strength * 0.38, 0.0, 0.85);
	}
	NORMAL = normalize(NORMAL + vec3(wave * 0.018, 0.0, cos(phase) * 0.018));
	METALLIC = source_metallic;
	SPECULAR = source_specular;
	ROUGHNESS = source_roughness;
}
