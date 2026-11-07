shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_disabled, diffuse_lambert;

uniform vec4 source_albedo : source_color = vec4(0.25, 0.48, 0.52, 0.7);
uniform float source_roughness = 0.3;
uniform float source_metallic = 0.0;
uniform float source_specular = 0.45;
uniform bool is_waterfall = true;
uniform vec3 waterfall_min;
uniform vec3 waterfall_size = vec3(1.0);
uniform float waterfall_glow = 0.0;
uniform float waterfall_phase = 0.0;
uniform float presentation_time = -1.0;
uniform vec3 accent_color = vec3(0.0);
uniform float accent_strength = 0.0;
varying vec3 water_position;

float hash21(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float noise2(vec2 p) {
    vec2 cell = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash21(cell), hash21(cell + vec2(1.0, 0.0)), f.x),
               mix(hash21(cell + vec2(0.0, 1.0)), hash21(cell + vec2(1.0)), f.x), f.y);
}

void vertex() {
    water_position = VERTEX;
}

void fragment() {
    vec3 p = (water_position - waterfall_min) / max(waterfall_size, vec3(0.001));
    float drop = clamp(1.0 - p.y, 0.0, 1.0);
    // Equal time intervals cover more distance lower down the falling sheet.
    float travel = sqrt(drop + 0.08) * 9.0 - waterfall_phase * 3.8;
    float across = p.z * waterfall_size.z;
    float sway = noise2(vec2(across * 7.0, waterfall_phase * 0.4)) * 0.7;
    float strands = noise2(vec2(across * 34.0 + sway, travel * 0.65));
    float broken = noise2(vec2(across * 64.0, travel * 5.0));
    float grain = noise2(vec2(across * 115.0, travel * 13.0));
    float white_water = clamp(0.25 + strands * 0.6 + broken * 0.3, 0.0, 1.0);
    float apertures = mix(1.0, smoothstep(0.16, 0.42, broken), drop * 0.55);
    ALBEDO = mix(source_albedo.rgb * 0.8, vec3(0.94, 0.98, 0.99), white_water);
    ALPHA = clamp((0.36 + strands * 0.48 + grain * 0.14) * apertures, 0.12, 0.96);
    NORMAL = normalize(NORMAL + vec3((strands - 0.5) * 0.22, (broken - 0.5) * 0.1, (grain - 0.5) * 0.16));
    vec3 night_color = mix(vec3(0.42, 0.60, 0.68), vec3(0.85, 0.92, 0.95), white_water);
    EMISSION = night_color * waterfall_glow * (0.35 + white_water * 0.55);
    METALLIC = source_metallic;
    SPECULAR = source_specular;
    ROUGHNESS = max(source_roughness, 0.28);
}
