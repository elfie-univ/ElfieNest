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
uniform bool is_waterfall = false;
uniform vec3 waterfall_min = vec3(0.0);
uniform vec3 waterfall_size = vec3(1.0);
uniform float waterfall_glow = 0.0;
uniform float waterfall_phase = 0.0;
uniform bool show_jet = false;
uniform bool show_central = false;
uniform float jet_height = 1.0;
uniform float jet_radius = 0.022;
uniform float show_time = 0.0;
uniform float presentation_time = -1.0;
uniform float jet_seed = 0.0;
uniform float water_pressure = 1.0;
uniform float flower_angle = 0.0;
uniform float flower_reach = 2.1;
uniform float inward_mix = 0.0;
uniform float inward_reach = 3.3;
varying vec3 water_position;

void vertex() {
	if (show_jet) {
		float t = UV.x;
		float angle = UV.y * 6.28318530718;
		vec3 radial = vec3(sin(angle),0.0,cos(angle));
        // A closed rounded crown and moving surface lobes replace the open pipe.
        float cap = clamp((t-0.84)/0.16,0.0,1.0);
        float crown = sqrt(max(0.0,1.0-cap*cap));
        float taper = mix(1.35,0.42,t)*crown;
        // Separate axial surges and angular irregularities: no rotating helix.
        float lobe = 1.0+0.12*sin(t*23.0-show_time*7.0+jet_seed)
                        +0.045*sin(angle*3.0+jet_seed)*sin(show_time*3.1);
        vec2 quiver = vec2(sin(t*18.0-show_time*4.0+jet_seed),cos(t*21.0-show_time*4.7+jet_seed));
        VERTEX = vec3(quiver.x*jet_radius*0.13*t,jet_height*t,quiver.y*jet_radius*0.13*t)
                   +radial*jet_radius*taper*lobe;
        NORMAL = normalize(radial+vec3(0.0,smoothstep(0.72,1.0,t)*3.0,0.0));
        if (inward_mix>0.0) {
            vec3 tangent=normalize(vec3(-inward_reach,4.0*jet_height*(1.0-2.0*t),0.0));
            vec3 side=vec3(0.0,0.0,1.0);
            vec3 arc_normal=normalize(cross(tangent,side));
            vec3 arc_radial=side*cos(angle)+arc_normal*sin(angle);
            vec3 arch=vec3(-inward_reach*t,4.0*jet_height*t*(1.0-t),0.0)+arc_radial*0.045;
            VERTEX=mix(VERTEX,arch,inward_mix);
            NORMAL=normalize(mix(NORMAL,arc_radial,inward_mix));
        }

    } else if (show_central) {
        float t = UV.x;
        vec3 direction = vec3(cos(flower_angle),0.0,sin(flower_angle));
        vec3 tangent = normalize(direction*flower_reach+vec3(0.0,4.0*jet_height*(1.0-2.0*t),0.0));
        vec3 side = vec3(-direction.z,0.0,direction.x);
        vec3 normal = normalize(cross(tangent,side));
        vec3 radial = side*cos(UV.y*6.2831853)+normal*sin(UV.y*6.2831853);
        float radius = mix(0.045,0.022,t)*(1.0+0.12*sin(t*42.0-show_time*9.0));
        VERTEX = direction*flower_reach*t+vec3(0.0,4.0*jet_height*t*(1.0-t),0.0)+radial*radius;
        NORMAL = radial;
	}
	water_position = VERTEX;
}

void fragment() {
	// Animate highlights and coverage within the authored jet/ring geometry.
	// Hidden authority scenes submit no water draws; no CPU clock is needed.
	float coordinate = is_ripple ? length(water_position.xy) * 18.0 : water_position.y * 24.0;
	float flow_time = (show_jet || show_central) ? show_time : (presentation_time >= 0.0 ? presentation_time : TIME);
	float phase = coordinate - flow_time * (show_jet ? 12.0 : (is_ripple ? 0.8 : -2.6));
	float wave = sin(phase);
	vec4 tint = source_albedo;
	if (use_source_texture) {
		tint *= texture(source_texture, UV + vec2(0.0, flow_time * 0.025));
	}
	ALBEDO = source_unshaded ? vec3(0.0) : tint.rgb;
	EMISSION = (source_unshaded ? tint.rgb : vec3(0.0)) + accent_color * accent_strength;
	ALPHA = ((show_jet || show_central) ? max(tint.a,0.28) : tint.a) * (0.94 + wave * 0.06);
    if (show_jet || show_central) {
        float flow = UV.x*65.0-flow_time*13.0+jet_seed;
        float streak = pow(0.5+0.5*sin(UV.y*25.1327+jet_seed),6.0)*(0.7+0.3*sin(flow));
        float bubbles = smoothstep(0.80,0.98,sin(flow+sin(UV.y*18.85)*2.0));
        float foam = show_jet ? smoothstep(0.70,0.97,UV.x)*(0.30+0.35*bubbles) : bubbles*0.12;
        vec2 grain_cell=floor(vec2(UV.y*48.0,UV.x*170.0-flow_time*22.0));
        float grain=fract(sin(dot(grain_cell,vec2(127.1,311.7)))*43758.5453);
        vec3 clear_water = vec3(0.82,0.9,0.94);
        ALBEDO = mix(clear_water,vec3(0.87,0.95,0.95),clamp(streak*0.35+foam,0.0,0.9));
        float night_coverage = clamp(accent_strength,0.0,1.0);
        ALPHA = clamp(0.72+night_coverage*0.10+streak*0.22+bubbles*0.12+foam*0.22,0.0,0.88)*water_pressure;
        ALPHA *= 0.28+0.72*smoothstep(0.15,0.7,grain);
        ALBEDO *= 0.78+grain*0.22;
        if (show_central) {
            float breakup = smoothstep(0.62,0.96,UV.x);
            ALPHA *= mix(1.0,0.25+0.75*smoothstep(-0.5,0.3,sin(flow)),breakup);
        }
        // Keep the whole stream readable; moving highlights add detail above that floor.
        EMISSION = (vec3(0.19)+accent_color*accent_strength*(0.60+streak*0.25+foam*0.25))*water_pressure*(0.7+grain*0.3);
    }
	// The authored rings are faint transparent water. Only their night pulse
	// gains coverage, so the illuminated ring remains readable without new mesh.
	if (is_ripple) {
		ALPHA = clamp(ALPHA + accent_strength * 0.38, 0.0, 0.85);
	}
	if (is_waterfall && waterfall_glow > 0.0) {
		// Full-sheet illumination. Downward-moving ribbons modulate a lit
		// base, so neither side nor the lower water curtain becomes black.
		vec3 p = (water_position - waterfall_min) / max(waterfall_size, vec3(0.001));
		float ribbon = 0.78 + 0.22 * sin(p.y * 18.0 + waterfall_phase * 3.2 + sin(p.z * 12.0));
		float color_phase = 0.5 + 0.5 * sin(waterfall_phase * 0.45 + p.z * 3.0 + p.y * 1.5);
		vec3 aqua = vec3(0.20, 0.72, 0.85);
		vec3 violet = vec3(0.62, 0.30, 0.82);
		EMISSION = mix(aqua, violet, color_phase) * ribbon * waterfall_glow;
		ALPHA = mix(ALPHA, max(ALPHA, 0.82), clamp(waterfall_glow, 0.0, 1.0));
	}
	NORMAL = normalize(NORMAL + vec3(wave * 0.018, 0.0, cos(phase) * 0.018));
	METALLIC = source_metallic;
	SPECULAR = source_specular;
	ROUGHNESS = source_roughness;
}
