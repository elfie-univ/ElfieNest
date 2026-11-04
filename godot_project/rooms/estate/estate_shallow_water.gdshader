shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_disabled, diffuse_lambert, specular_schlick_ggx;

uniform vec4 source_albedo : source_color;
uniform float source_roughness = 0.22;
uniform float source_metallic = 0.02;
uniform float source_specular = 0.5;
uniform float source_clearcoat = 0.0;
uniform float source_coat_roughness = 0.0;
uniform bool is_spillway = false;
uniform float wave_amplitude = 0.025;
uniform float detail_amplitude = 0.0;
uniform float wave_speed = 0.22;
uniform float water_opacity;
uniform vec3 water_tint : source_color = vec3(0.16, 0.34, 0.35);
uniform vec3 accent_color = vec3(0.0);
uniform float accent_strength = 0.0;
uniform bool fountain_waves = false;
uniform vec3 fountain_center;
uniform float pool_radius = 5.0;
uniform float channel_end_radius = 8.0;
uniform float show_time = 0.0;
uniform float presentation_time = -1.0;
uniform float show_night = 0.0;
uniform float flower_height = 0.0;
uniform float flower_reach = 2.1;
uniform vec4 flower_colors[8];
uniform vec4 impacts[17];
uniform vec4 impact_colors[17];
varying vec3 water_position;
varying vec3 world_water_position;

void vertex() {
	// Coordinates only: no vertex displacement or changes to physical shape.
	water_position = VERTEX;
    world_water_position = (MODEL_MATRIX*vec4(VERTEX,1.0)).xyz;
}

void fragment() {
	float speed = is_spillway ? 1.1 : wave_speed;
	float phase = (presentation_time >= 0.0 ? presentation_time : TIME) * speed;
	vec2 slope = vec2(
		cos(water_position.x * 2.1 + water_position.z * 1.3 - phase),
		sin(water_position.z * 2.7 - water_position.x * 0.7 + phase * 0.71)
	) * wave_amplitude;
	slope += vec2(sin(water_position.x * 7.1 + water_position.z * 5.3 - phase * 1.3), cos(water_position.z * 6.7 - water_position.x * 4.9 + phase * 0.9)) * detail_amplitude;
	vec3 ripple = mat3(VIEW_MATRIX * MODEL_MATRIX) * vec3(slope.x, 0.0, slope.y);
	NORMAL = normalize(NORMAL + ripple);
	if (dot(NORMAL, VIEW) < 0.0) {
		NORMAL = -NORMAL;
	}
	ALBEDO = mix(source_albedo.rgb, water_tint, 0.65);
	EMISSION = accent_color * accent_strength * 0.12;
    if (fountain_waves) {
        vec2 p = world_water_position.xz-fountain_center.xz;
        float radius = length(p);
        // Continuous wavefronts are clipped by the real pool/channel mesh.
        float travel = show_time+0.35*sin(show_time*6.2831853/80.0);
        float spacing = is_spillway ? max((channel_end_radius-pool_radius)/2.0,0.6) : 1.15;
        float coordinate = is_spillway ? (radius-pool_radius)/spacing+pool_radius/1.15 : radius/spacing;
        float front = abs(fract(coordinate-travel*0.55)-0.5)*spacing;
        float pulse = exp(-pow(front/0.045,2.0));
        float fade = is_spillway ? 1.0-smoothstep(pool_radius,channel_end_radius,radius)*0.85 : 1.0;
        float wall = is_spillway ? 0.0 : exp(-pow((radius-(pool_radius-0.06))/0.09,2.0));
        float arrival = exp(-pow(abs(fract(pool_radius/1.15-travel*0.55)-0.5)*1.15/0.13,2.0));
        ALBEDO += vec3(0.09)*pulse*fade;
        EMISSION += accent_color*show_night*(pulse*0.65*fade+wall*arrival*0.35);
        if (!is_spillway) {
            for (int i=0;i<17;i++) {
                vec2 offset=p-impacts[i].xy;
                float d=length(offset);
                float age=fract(show_time*1.8+float(i)*0.137);
                float rim=exp(-pow((d-(impacts[i].z*0.4+age*impacts[i].z*2.0))/0.025,2.0))*(1.0-age);
                float foam=exp(-d*d/(impacts[i].z*impacts[i].z))*(0.60+0.25*sin(show_time*17.0+float(i)));
                float impact=impacts[i].w;
                ALBEDO=mix(ALBEDO,vec3(0.78,0.9,0.93),clamp((foam+rim*0.4)*impact,0.0,0.85));
                EMISSION+=(vec3(0.12)*(foam+rim*0.3)+impact_colors[i].rgb*show_night*(foam*0.7+rim*0.28))*impact;
            }
        }
    }
	float fresnel = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 3.0);
	ALPHA = clamp(water_opacity + fresnel * 0.12, 0.5, 0.78);
	METALLIC = source_metallic;
	SPECULAR = source_specular;
	ROUGHNESS = source_roughness;
	CLEARCOAT = source_clearcoat;
	float coat = max(source_coat_roughness, 0.0525);
	CLEARCOAT_ROUGHNESS = clamp((coat * coat - 0.001) / 0.099, 0.0, 1.0);
}
