class_name ActorAppearance
extends RefCounted

const SPECIES_CATALOG := preload("res://runtime/species_catalog.gd")
const BASE_COLLISION_RADIUS := 0.34
const BASE_COLLISION_HEIGHT := 1.72
const MAX_REGION_ACCENTS := 2
const COLORABLE_REGION_IDS := [0, 2, 3, 5, 7, 8, 9, 10, 11, 12]
const SOURCE_FUR_ANCHORS := {
	"dog": Color("d4a672"),
	"fox": Color("ba662f"),
}
const FUR_DISTANCE_START := {
	"dog": 0.16,
	"fox": 0.12,
}
const FUR_DISTANCE_END := {
	"dog": 0.82,
	"fox": 0.58,
}
const REGION_MID_LUMA := {
	"dog": 0.62,
	"fox": 0.56,
}
const REGION_DEBUG_SHADER_CODE := """
shader_type spatial;
render_mode unshaded, cull_disabled, blend_mix, depth_draw_never;

// The reviewed region geometry samples this texture only for the fox inner-ear
// exclusion. The opaque production fragment assembled below also reads the
// same original UV texture as the source for coat tone transfer.
uniform sampler2D appearance_region_source_texture : source_color;
uniform bool use_appearance_region_source_texture = false;
uniform int appearance_species_id = 0;
uniform int appearance_selected_region = -1;
uniform vec4 appearance_region_debug_color : source_color = vec4(1.0);
uniform vec3 appearance_region_coordinate_scale = vec3(1.0);

varying vec3 appearance_region_position;
varying vec3 appearance_region_normal;
varying vec2 appearance_region_uv;
varying float appearance_tail_bone;
varying float appearance_leg_bone;
varying float appearance_lower_leg_bone;
varying float appearance_arm_bone;
varying float appearance_forearm_bone;
varying float appearance_head_bone;
varying float appearance_head_top_bone;

float joint_weight(uvec4 indices, vec4 weights, uint joint_id) {
    return (indices.x == joint_id ? weights.x : 0.0)
        + (indices.y == joint_id ? weights.y : 0.0)
        + (indices.z == joint_id ? weights.z : 0.0)
        + (indices.w == joint_id ? weights.w : 0.0);
}

float joint_weight_range(uvec4 indices, vec4 weights, uint first_id, uint last_id) {
    float result = 0.0;
    result += (indices.x >= first_id && indices.x <= last_id) ? weights.x : 0.0;
    result += (indices.y >= first_id && indices.y <= last_id) ? weights.y : 0.0;
    result += (indices.z >= first_id && indices.z <= last_id) ? weights.z : 0.0;
    result += (indices.w >= first_id && indices.w <= last_id) ? weights.w : 0.0;
    return result;
}

void vertex() {
    // Region thresholds are authored in the evaluated scene-space used by the
    // approved V9 region experiment. This keeps them stable across the GLB's
    // centimetre armature scale and the actor's runtime transform.
    vec3 evaluated_position = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
    appearance_region_position = evaluated_position
        / max(appearance_region_coordinate_scale, vec3(0.0001));
    // Keep the exact region coordinate semantics from the reviewed phase-3
    // experiment. Region thresholds and normals are evaluated in the mesh's
    // original local frame; do not transform the normal through MODEL_MATRIX.
    appearance_region_normal = NORMAL;
    appearance_region_uv = UV;
    uvec4 bone_indices = BONE_INDICES;
    vec4 bone_weights = BONE_WEIGHTS;
    appearance_leg_bone = joint_weight_range(bone_indices, bone_weights, 1u, 10u);
    appearance_lower_leg_bone = joint_weight_range(bone_indices, bone_weights, 2u, 5u)
        + joint_weight_range(bone_indices, bone_weights, 7u, 10u);
    if (appearance_species_id == 0) {
        appearance_tail_bone = joint_weight(bone_indices, bone_weights, 33u);
        appearance_arm_bone = joint_weight_range(bone_indices, bone_weights, 14u, 21u)
            + joint_weight_range(bone_indices, bone_weights, 25u, 32u);
        appearance_forearm_bone = joint_weight_range(bone_indices, bone_weights, 16u, 21u)
            + joint_weight_range(bone_indices, bone_weights, 27u, 32u);
        appearance_head_bone = joint_weight(bone_indices, bone_weights, 23u);
        appearance_head_top_bone = joint_weight(bone_indices, bone_weights, 24u);
    } else {
        appearance_tail_bone = joint_weight(bone_indices, bone_weights, 41u);
        appearance_arm_bone = joint_weight_range(bone_indices, bone_weights, 14u, 25u)
            + joint_weight_range(bone_indices, bone_weights, 29u, 40u);
        appearance_forearm_bone = joint_weight_range(bone_indices, bone_weights, 16u, 25u)
            + joint_weight_range(bone_indices, bone_weights, 31u, 40u);
        appearance_head_bone = joint_weight(bone_indices, bone_weights, 27u);
        appearance_head_top_bone = joint_weight(bone_indices, bone_weights, 28u);
    }
}

float soft_band(float value, float lower, float upper, float feather) {
    float rise = smoothstep(lower, lower + feather, value);
    float fall = 1.0 - smoothstep(upper - feather, upper, value);
    return rise * fall;
}

float soft_abs_band(float value, float radius, float feather) {
    return 1.0 - smoothstep(radius, radius + feather, abs(value));
}

float appearance_head_tuft() {
    // Only the small central tuft that protrudes above the crown. The rounded
    // footprint includes the rear half visible in a top view without taking
    // the surrounding crown or forehead with it.
    float crown = appearance_species_id == 1
        ? soft_band(appearance_region_position.y, 1.63, 1.76, 0.018)
        : soft_band(appearance_region_position.y, 1.80, 1.97, 0.020);
    float depth_center = appearance_species_id == 1 ? 0.45 : 0.25;
    float depth_radius = appearance_species_id == 1 ? 0.26 : 0.28;
    float width_radius = appearance_species_id == 1 ? 0.12 : 0.085;
    float ellipse_distance =
        pow(appearance_region_position.x / width_radius, 2.0)
        + pow((appearance_region_position.z - depth_center) / depth_radius, 2.0);
    float center = 1.0 - smoothstep(0.48, 1.0, ellipse_distance);
    float tuft_bone = max(appearance_head_top_bone, appearance_head_bone * 0.65);
    return crown * center * smoothstep(0.05, 0.22, tuft_bone);
}

float appearance_forehead_mark_zone() {
    float forehead = appearance_species_id == 1
        ? soft_band(appearance_region_position.y, 1.52, 1.68, 0.020)
        : soft_band(appearance_region_position.y, 1.62, 1.77, 0.020);
    float center = appearance_species_id == 1
        ? soft_abs_band(appearance_region_position.x, 0.14, 0.018)
        : soft_abs_band(appearance_region_position.x, 0.105, 0.018);
    float front = appearance_species_id == 1
        ? smoothstep(0.18, 0.30, appearance_region_position.z)
            * smoothstep(0.12, 0.24, appearance_region_normal.z)
        : smoothstep(0.22, 0.34, appearance_region_position.z)
            * smoothstep(0.16, 0.27, appearance_region_normal.z);
    float tuft_clear = 1.0 - smoothstep(0.10, 0.34, appearance_head_tuft());
    return forehead * center * front * tuft_clear;
}

float appearance_source_luminance() {
    if (!use_appearance_region_source_texture) return 0.0;
    return dot(texture(appearance_region_source_texture, appearance_region_uv).rgb, vec3(0.299, 0.587, 0.114));
}

float appearance_source_chroma() {
    if (!use_appearance_region_source_texture) return 1.0;
    vec3 source = texture(appearance_region_source_texture, appearance_region_uv).rgb;
    float high = max(max(source.r, source.g), source.b);
    float low = min(min(source.r, source.g), source.b);
    return high - low;
}

float appearance_fox_inner_white_ear() {
    float white = smoothstep(0.62, 0.80, appearance_source_luminance());
    float low_chroma = 1.0 - smoothstep(0.05, 0.16, appearance_source_chroma());
    return white * low_chroma;
}

float appearance_ear_pair() {
    float side = smoothstep(0.255, 0.34, abs(appearance_region_position.x));
    float height = soft_band(appearance_region_position.y, 1.36, 1.82, 0.035);
    float front = smoothstep(0.0, 0.16, appearance_region_position.z)
        * smoothstep(-0.04, 0.12, appearance_region_normal.z);
    float surface = appearance_species_id == 1
        ? (1.0 - appearance_fox_inner_white_ear())
        : front;
    return side * height * surface;
}

float appearance_ear_tip_pair() {
    float radius = abs(appearance_region_position.x);
    float side = appearance_species_id == 0
        ? smoothstep(0.31, 0.40, radius)
            * (1.0 - smoothstep(0.58, 0.64, radius))
        : smoothstep(0.27, 0.33, radius)
            * (1.0 - smoothstep(0.45, 0.51, radius));
    float height = appearance_species_id == 0
        ? soft_band(appearance_region_position.y, 1.10, 1.38, 0.030)
        : soft_band(appearance_region_position.y, 1.76, 2.00, 0.030);
    float surface = smoothstep(-0.04, 0.16, appearance_region_position.z);
    return side * height * surface;
}

float appearance_cheek_fluff() {
    float face = appearance_species_id == 0
        ? soft_band(appearance_region_position.y, 1.23, 1.44, 0.025)
        : soft_band(appearance_region_position.y, 1.18, 1.43, 0.025);
    float inner_radius = appearance_species_id == 1 ? 0.16 : 0.13;
    float outer_radius = appearance_species_id == 1 ? 0.36 : 0.30;
    float sides = smoothstep(inner_radius, inner_radius + 0.035, abs(appearance_region_position.x))
        * (1.0 - smoothstep(outer_radius - 0.035, outer_radius, abs(appearance_region_position.x)));
    float front = appearance_species_id == 0
        ? smoothstep(0.20, 0.38, appearance_region_position.z)
            * smoothstep(0.22, 0.42, appearance_region_normal.z)
        : smoothstep(0.12, 0.24, appearance_region_position.z)
            * smoothstep(0.10, 0.22, appearance_region_normal.z);
    return face * sides * front * smoothstep(0.05, 0.28, appearance_head_bone);
}

float appearance_chest_tuft() {
    float chest_y = appearance_region_position.y + (appearance_species_id == 1 ? 0.0 : -0.04);
    vec2 point = vec2(appearance_region_position.x, chest_y);
    float left_lobe = 1.0 - smoothstep(
        1.0, 1.06, length((point - vec2(-0.065, 0.98)) / vec2(0.085, 0.065))
    );
    float right_lobe = 1.0 - smoothstep(
        1.0, 1.06, length((point - vec2(0.065, 0.98)) / vec2(0.085, 0.065))
    );
    float point_progress = smoothstep(0.78, 0.91, chest_y);
    float point_width = mix(0.0, 0.065, point_progress);
    float point_tip = soft_band(chest_y, 0.76, 0.99, 0.020)
        * soft_abs_band(appearance_region_position.x, point_width, 0.016);
    float heart = max(max(left_lobe, right_lobe), point_tip);
    return heart * smoothstep(0.06, 0.20, appearance_region_position.z)
        * smoothstep(0.14, 0.28, appearance_region_normal.z);
}

float appearance_belly_center() {
    float center_y = appearance_species_id == 1 ? 0.70 : 0.69;
    float half_height = appearance_species_id == 1 ? 0.28 : 0.27;
    float vertical = abs((appearance_region_position.y - center_y) / half_height);
    float inside = 1.0 - smoothstep(0.78, 1.0, vertical);
    float bulge = sqrt(max(0.0, 1.0 - min(vertical * vertical, 1.0)));
    float max_width = appearance_species_id == 1 ? 0.17 : 0.16;
    float width = mix(0.045, max_width, bulge);
    float center = 1.0 - smoothstep(width, width + 0.025, abs(appearance_region_position.x));
    return inside * center
        * smoothstep(0.12, 0.28, appearance_region_position.z)
        * smoothstep(0.42, 0.56, appearance_region_normal.z)
        * (1.0 - smoothstep(0.14, 0.20, abs(appearance_region_position.x)));
}

float appearance_forearm_paw_pair() {
    return smoothstep(0.18, 0.52, appearance_forearm_bone);
}

float appearance_elbow_cuff_pair() {
    // This is a patch on the back of the elbow, not a ring around the limb.
    // Keep this geometry identical to the reviewed experiment, including the
    // species-specific center/radius and the rear-facing normal gate.
    float center_x = appearance_species_id == 1 ? 0.265 : 0.270;
    float center_y = appearance_species_id == 1 ? 0.76 : 0.80;
    float radius_x = appearance_species_id == 1 ? 0.105 : 0.115;
    float radius_y = appearance_species_id == 1 ? 0.115 : 0.120;
    float dx = (abs(appearance_region_position.x) - center_x) / radius_x;
    float dy = (appearance_region_position.y - center_y) / radius_y;
    float circle = 1.0 - smoothstep(0.72, 1.0, dx * dx + dy * dy);
    float elbow_surface = smoothstep(0.04, 0.28, -appearance_region_normal.z);
    return circle * elbow_surface * smoothstep(0.18, 0.52, appearance_arm_bone);
}

float appearance_lower_leg_foot_pair() {
    float leg = soft_band(appearance_region_position.y, -0.04, 0.38, 0.035);
    return leg * smoothstep(0.22, 0.58, appearance_lower_leg_bone);
}

float appearance_knee_cuff_pair() {
    // A front-facing circular knee patch. Keep the reviewed experiment's
    // species-specific footprint so it cannot grow into the rear leg or tail.
    float center_x = appearance_species_id == 1 ? 0.21 : 0.18;
    float center_y = appearance_species_id == 1 ? 0.31 : 0.36;
    float radius_x = appearance_species_id == 1 ? 0.060 : 0.100;
    float radius_y = appearance_species_id == 1 ? 0.058 : 0.090;
    float dx = (abs(appearance_region_position.x) - center_x) / radius_x;
    float dy = (appearance_region_position.y - center_y) / radius_y;
    float circle = 1.0 - smoothstep(0.72, 1.0, dx * dx + dy * dy);
    float front_surface = smoothstep(0.08, 0.24, appearance_region_position.z)
        * smoothstep(0.18, 0.38, appearance_region_normal.z);
    return circle * front_surface * smoothstep(0.18, 0.52, appearance_leg_bone);
}

float appearance_tail_tip() {
    float tail_progress = length(vec2(appearance_region_position.x, appearance_region_position.z));
    float endpoint = appearance_species_id == 0
        ? smoothstep(0.56, 0.80, tail_progress)
        : smoothstep(0.64, 0.90, tail_progress);
    return endpoint * smoothstep(0.24, 0.66, appearance_tail_bone);
}

float appearance_tail_underside() {
    float tail_progress = length(vec2(appearance_region_position.x, appearance_region_position.z));
    float not_tip = 1.0 - smoothstep(0.74, 0.92, tail_progress);
    float underside = smoothstep(0.08, 0.32, -appearance_region_normal.y);
    return not_tip * underside * smoothstep(0.24, 0.66, appearance_tail_bone);
}

float appearance_region_alpha(int region_id) {
    if (region_id == 0) return appearance_head_tuft();
    if (region_id == 1) return appearance_forehead_mark_zone();
    if (region_id == 2) return appearance_ear_pair();
    if (region_id == 3) return appearance_ear_tip_pair();
    if (region_id == 4) return appearance_cheek_fluff();
    if (region_id == 5) return appearance_chest_tuft();
    if (region_id == 6) return appearance_belly_center();
    if (region_id == 7) return appearance_forearm_paw_pair();
    if (region_id == 8) return appearance_elbow_cuff_pair();
    if (region_id == 9) return appearance_lower_leg_foot_pair();
    if (region_id == 10) return appearance_knee_cuff_pair();
    if (region_id == 11) return appearance_tail_tip();
    if (region_id == 12) return appearance_tail_underside();
    return 0.0;
}

int appearance_classify_region() {
    // This is the phase-3 experiment's overlap priority verbatim. Smaller,
    // more specific regions own overlaps before their broader parent bands.
    if (appearance_region_alpha(0) > 0.52) return 0;
    if (appearance_region_alpha(1) > 0.52) return 1;
    if (appearance_region_alpha(3) > 0.52) return 3;
    if (appearance_region_alpha(2) > 0.52) return 2;
    if (appearance_region_alpha(4) > 0.52) return 4;
    if (appearance_region_alpha(5) > 0.52) return 5;
    if (appearance_region_alpha(6) > 0.52) return 6;
    if (appearance_region_alpha(8) > 0.52) return 8;
    if (appearance_region_alpha(10) > 0.52) return 10;
    if (appearance_region_alpha(7) > 0.52) return 7;
    if (appearance_region_alpha(9) > 0.52) return 9;
    if (appearance_region_alpha(11) > 0.52) return 11;
    if (appearance_region_alpha(12) > 0.52) return 12;
    return -1;
}

void fragment() {
    int debug_region = appearance_selected_region >= 0
        ? appearance_selected_region
        : appearance_classify_region();
    float debug_selected = debug_region >= 0
        ? clamp(appearance_region_alpha(debug_region), 0.0, 1.0)
        : 0.0;
    ALBEDO = appearance_region_debug_color.rgb;
    ALPHA = debug_selected * 0.78;
}
"""

const APPEARANCE_SHADER_SUFFIX := """

float appearance_luminance_v9(vec3 color_value) {
    return dot(color_value, vec3(0.2126, 0.7152, 0.0722));
}

float appearance_smoothstep_v9(float edge0, float edge1, float value) {
    float unit_value = clamp((value - edge0) / (edge1 - edge0), 0.0, 1.0);
    return unit_value * unit_value * (3.0 - 2.0 * unit_value);
}

vec3 appearance_linear_to_srgb(vec3 color_value) {
    vec3 lower = color_value * 12.92;
    vec3 upper = 1.055 * pow(max(color_value, vec3(0.0)), vec3(1.0 / 2.4)) - 0.055;
    return mix(lower, upper, step(vec3(0.0031308), color_value));
}

vec3 appearance_srgb_to_linear(vec3 color_value) {
    vec3 lower = color_value / 12.92;
    vec3 upper = pow((max(color_value, vec3(0.0)) + 0.055) / 1.055, vec3(2.4));
    return mix(lower, upper, step(vec3(0.04045), color_value));
}

vec3 appearance_tone_from_mid(vec3 source, vec3 target, float source_mid_luma) {
    float source_luma = appearance_luminance_v9(source);
    float target_luma = max(appearance_luminance_v9(target), 0.001);
    vec3 target_chroma = target / target_luma;
    float relative_luma = pow(source_luma / max(source_mid_luma, 0.001), 0.78);
    float output_luma = clamp(target_luma * relative_luma, 0.015, 0.985);
    return clamp(target_chroma * output_luma, vec3(0.0), vec3(1.0));
}

vec3 appearance_base_coat_transfer(vec3 source) {
    vec3 target = appearance_linear_to_srgb(appearance_base_target_color.rgb);
    vec3 source_anchor = appearance_linear_to_srgb(appearance_source_fur_anchor.rgb);
    float source_luma = appearance_luminance_v9(source);
    float high_channel = max(source.r, max(source.g, source.b));
    float low_channel = min(source.r, min(source.g, source.b));
    float neutrality = low_channel / max(high_channel, 0.001);
    float dark_feature = (
        (1.0 - appearance_smoothstep_v9(0.035, 0.14, source_luma))
        * appearance_smoothstep_v9(0.55, 0.88, neutrality)
    );
    float light_region = (
        appearance_smoothstep_v9(0.74, 0.90, source_luma)
        * appearance_smoothstep_v9(0.80, 0.94, neutrality)
    );
    vec3 source_direction = source / max(high_channel, 0.001);
    float anchor_high = max(source_anchor.r, max(source_anchor.g, source_anchor.b));
    vec3 anchor_direction = source_anchor / max(anchor_high, 0.001);
    float fur_distance = length(source_direction - anchor_direction);
    float fur_similarity = 1.0 - appearance_smoothstep_v9(
        appearance_fur_distance_start,
        appearance_fur_distance_end,
        fur_distance
    );
    vec3 recolored = appearance_tone_from_mid(
        source,
        target,
        max(appearance_luminance_v9(source_anchor), 0.001)
    );
    float preserve = clamp(max(dark_feature, light_region), 0.0, 1.0);
    return mix(source, recolored, fur_similarity * (1.0 - preserve));
}

vec3 appearance_local_transfer(vec3 source, vec4 target_linear) {
    vec3 target = appearance_linear_to_srgb(target_linear.rgb);
    return appearance_tone_from_mid(source, target, appearance_region_mid_luma);
}

float appearance_owned_region_alpha(int requested_region, int owner_region) {
    if (requested_region < 0 || requested_region != owner_region) return 0.0;
    return smoothstep(
        0.50,
        0.82,
        clamp(appearance_region_alpha(requested_region), 0.0, 1.0)
    );
}

float appearance_disc(vec2 point, float radius, float feather) {
    return 1.0 - smoothstep(radius - feather, radius + feather, length(point));
}

float appearance_stroke(vec2 point, vec2 start, vec2 finish, float width) {
    vec2 along = finish - start;
    float projection = clamp(
        dot(point - start, along) / max(dot(along, along), 0.0001),
        0.0,
        1.0
    );
    return 1.0 - smoothstep(
        width,
        width + 0.035,
        length(point - mix(start, finish, projection))
    );
}

float appearance_dot_mark(vec2 point, vec2 center, float radius) {
    return 1.0 - smoothstep(radius, radius + 0.035, length(point - center));
}

float appearance_marking_shape(vec2 point, int marking) {
    if (marking == 1) {
        float outer = 1.0 - smoothstep(0.48, 0.58, length(point));
        float cutout = 1.0 - smoothstep(0.43, 0.53, length(point - vec2(0.20, 0.03)));
        return outer * (1.0 - cutout);
    }
    if (marking == 2) {
        float upper = appearance_stroke(point, vec2(-0.35, 0.28), vec2(0.30, 0.28), 0.07);
        float middle = appearance_stroke(point, vec2(0.30, 0.28), vec2(-0.30, -0.04), 0.07);
        float lower = appearance_stroke(point, vec2(-0.30, -0.04), vec2(0.35, -0.28), 0.07);
        return max(max(upper, middle), lower);
    }
    if (marking == 3) {
        float first = abs(length(point) - 0.28);
        float second = abs(length(point - vec2(0.12, 0.0)) - 0.18);
        return max(
            1.0 - smoothstep(0.035, 0.075, first),
            1.0 - smoothstep(0.035, 0.075, second)
        );
    }
    if (marking == 4) {
        return max(
            max(
                appearance_dot_mark(point, vec2(-0.28, 0.20), 0.08),
                appearance_dot_mark(point, vec2(0.02, 0.32), 0.06)
            ),
            max(
                appearance_dot_mark(point, vec2(0.25, 0.10), 0.075),
                appearance_dot_mark(point, vec2(-0.05, -0.20), 0.055)
            )
        );
    }
    if (marking == 5) {
        return max(
            appearance_dot_mark(point, vec2(-0.25, 0.08), 0.12),
            appearance_stroke(point, vec2(-0.12, 0.02), vec2(0.40, -0.22), 0.06)
        );
    }
    if (marking == 6) {
        return max(
            max(
                appearance_stroke(point, vec2(0.0, -0.38), vec2(0.0, 0.38), 0.06),
                appearance_stroke(point, vec2(-0.25, 0.24), vec2(0.25, 0.24), 0.05)
            ),
            appearance_stroke(point, vec2(-0.20, -0.20), vec2(0.22, -0.20), 0.05)
        );
    }
    if (marking == 7) {
        return 1.0 - smoothstep(0.55, 0.65, abs(point.x) + abs(point.y));
    }
    if (marking == 8) {
        float angle = atan(point.y, point.x);
        float star_radius = 0.43 + 0.20 * cos(5.0 * angle);
        return 1.0 - smoothstep(
            star_radius - 0.045,
            star_radius + 0.045,
            length(point)
        );
    }
    if (marking == 9) {
        return max(
            max(
                appearance_stroke(point, vec2(-0.28, 0.35), vec2(0.05, 0.05), 0.06),
                appearance_stroke(point, vec2(0.05, 0.05), vec2(-0.12, 0.05), 0.06)
            ),
            appearance_stroke(point, vec2(-0.12, 0.05), vec2(0.25, -0.35), 0.06)
        );
    }
    if (marking == 10) {
        return 1.0 - smoothstep(
            0.055,
            0.10,
            abs(point.y - 0.20 * sin(point.x * 5.0))
        );
    }
    if (marking == 11) {
        return max(0.0, 1.0 - smoothstep(0.035, 0.075, abs(length(point) - 0.34)));
    }
    return 0.0;
}

float appearance_cheek_mark_shape(int marking) {
    float center_x = appearance_species_id == 1 ? 0.245 : 0.205;
    float center_y = appearance_species_id == 1 ? 1.30 : 1.335;
    vec2 point = vec2(
        (abs(appearance_region_position.x) - center_x) / 0.060,
        (appearance_region_position.y - center_y) / 0.060
    );
    if (marking == 12) {
        return appearance_disc(point, 0.72, 0.10);
    }
    if (marking == 13) {
        float spot_a = appearance_disc(point - vec2(-0.34, 0.12), 0.16, 0.045);
        float spot_b = appearance_disc(point - vec2(0.18, 0.25), 0.13, 0.040);
        float spot_c = appearance_disc(point - vec2(0.38, -0.20), 0.11, 0.035);
        return max(spot_a, max(spot_b, spot_c));
    }
    if (marking == 15) {
        return appearance_disc(point - vec2(0.18, -0.06), 0.16, 0.045);
    }
    return 0.0;
}

float appearance_heart_shape() {
    float center_y = appearance_marking_placement == 6
        ? (appearance_species_id == 1 ? 0.70 : 0.69)
        : (appearance_species_id == 1 ? 0.92 : 0.96);
    float width = appearance_marking_placement == 6 ? 0.115 : 0.090;
    float height = appearance_marking_placement == 6 ? 0.165 : 0.120;
    float scale_value = clamp(appearance_marking_scale, 0.5, 1.25);
    vec2 point = vec2(
        appearance_region_position.x / (width * scale_value),
        (appearance_region_position.y - center_y) / (height * scale_value)
    );
    point.y += 0.10;
    float base = point.x * point.x + point.y * point.y - 0.55;
    float implicit_heart = base * base * base
        - point.x * point.x * point.y * point.y * point.y;
    return 1.0 - smoothstep(-0.015, 0.045, implicit_heart);
}

float appearance_marking_safe_region() {
    if (
        appearance_marking_placement == 1
        || appearance_marking_placement == 2
        || appearance_marking_placement == 3
    ) return appearance_region_alpha(1);
    if (appearance_marking_placement == 4) return appearance_region_alpha(4);
    if (appearance_marking_placement == 5) return appearance_region_alpha(5);
    if (appearance_marking_placement == 6) return appearance_region_alpha(6);
    return 0.0;
}

float appearance_safe_mark_alpha() {
    if (appearance_marking_id <= 0 || appearance_marking_placement <= 0) return 0.0;
    float safe_region = smoothstep(
        0.36,
        0.72,
        clamp(appearance_marking_safe_region(), 0.0, 1.0)
    );
    vec2 point = (
        appearance_region_position.xy - appearance_marking_zone.xy
    ) / max(appearance_marking_zone.w * appearance_marking_scale, 0.01);
    float symbol = appearance_marking_shape(point, appearance_marking_id);
    if (
        appearance_marking_id == 12
        || appearance_marking_id == 13
        || appearance_marking_id == 15
    ) symbol = appearance_cheek_mark_shape(appearance_marking_id);
    if (appearance_marking_id == 14) symbol = appearance_heart_shape();
    return safe_region * symbol;
}

void fragment() {
    vec3 source = appearance_linear_to_srgb(
        texture(appearance_region_source_texture, appearance_region_uv).rgb
    );
    vec3 output_color = appearance_base_coat_transfer(source);
    int owner_region = appearance_classify_region();

    float accent_0 = appearance_owned_region_alpha(
        appearance_accent_region_0,
        owner_region
    ) * appearance_accent_intensity_0;
    vec3 accent_color_0 = appearance_local_transfer(source, appearance_accent_color_0);
    output_color = mix(output_color, accent_color_0, clamp(accent_0, 0.0, 1.0));

    float accent_1 = appearance_owned_region_alpha(
        appearance_accent_region_1,
        owner_region
    ) * appearance_accent_intensity_1;
    vec3 accent_color_1 = appearance_local_transfer(source, appearance_accent_color_1);
    output_color = mix(output_color, accent_color_1, clamp(accent_1, 0.0, 1.0));

    float mark_alpha = appearance_safe_mark_alpha() * appearance_marking_intensity;
    vec3 mark_color = appearance_local_transfer(source, appearance_marking_color);
    output_color = mix(output_color, mark_color, clamp(mark_alpha, 0.0, 1.0));

    ALBEDO = appearance_srgb_to_linear(clamp(output_color, vec3(0.0), vec3(1.0)));
    // Opaque by construction: never declare, read or write ALPHA. This keeps
    // the tail and every other rear surface in the normal depth pipeline.
}
"""


static func apply(
	visual_root: Node3D,
	collision_shape: CollisionShape3D,
	appearance: Dictionary,
	species_id: String = "",
) -> void:
	var height_scale := _appearance_scale(
		appearance.get("height_scale", appearance.get("height", "standard")),
		{"short": 0.92, "standard": 1.0, "tall": 1.08},
	)
	var build_scale := _appearance_scale(
		appearance.get("build_scale", appearance.get("build", "standard")),
		{"slim": 0.92, "standard": 1.0, "plump": 1.08},
	)
	height_scale = clampf(height_scale, 0.82, 1.18)
	build_scale = clampf(build_scale, 0.85, 1.15)
	var authored_visual_scale := _authored_scale(visual_root, &"actor_authored_scale")
	visual_root.scale = Vector3(
		authored_visual_scale.x * build_scale,
		authored_visual_scale.y * height_scale,
		authored_visual_scale.z * build_scale,
	)

	var authored_collision_scale := _authored_scale(
		collision_shape,
		&"actor_authored_scale",
	)
	collision_shape.scale = Vector3(
		authored_collision_scale.x * build_scale,
		authored_collision_scale.y * height_scale,
		authored_collision_scale.z * build_scale,
	)
	collision_shape.position.y = (
		BASE_COLLISION_HEIGHT
		* authored_collision_scale.y
		* height_scale
		* 0.5
	)
	var bindings: Dictionary = SPECIES_CATALOG.appearance_bindings(species_id)
	_apply_bone_scales(
		visual_root,
		appearance.get("bone_scales", {}),
		bindings.get("bone_scales", {}),
	)
	_apply_blend_shapes(
		visual_root,
		appearance.get("blend_shapes", {}),
		bindings.get("blend_shapes", {}),
	)
	_apply_material_parameters(
		visual_root,
		appearance.get("material_parameters", {}),
		bindings,
		species_id,
	)


static func apply_region_debug(
	visual_root: Node3D,
	species_id: String,
	selected_region: int,
	debug_color: Color,
) -> void:
	"""Render one reviewed phase-3 region using the production shader functions."""
	var shader := Shader.new()
	shader.code = REGION_DEBUG_SHADER_CODE
	for node in visual_root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		var material := ShaderMaterial.new()
		material.shader = shader
		material.set_shader_parameter("appearance_species_id", 0 if species_id == "dog" else 1)
		material.set_shader_parameter(
			"appearance_region_coordinate_scale",
			visual_root.scale,
		)
		material.set_shader_parameter("appearance_selected_region", selected_region)
		material.set_shader_parameter("appearance_region_debug_color", debug_color)
		var source_material: Material = mesh_instance.get_active_material(0)
		if source_material is BaseMaterial3D:
			var base_material := source_material as BaseMaterial3D
			var region_source_texture: Texture2D = base_material.emission_texture
			if region_source_texture == null:
				region_source_texture = base_material.albedo_texture
			if region_source_texture != null:
				material.set_shader_parameter(
					"appearance_region_source_texture",
					region_source_texture,
				)
				material.set_shader_parameter(
					"use_appearance_region_source_texture",
					true,
				)
		mesh_instance.material_overlay = material


static func ground_visual_to_plane(visual_root: Node3D, ground_y: float) -> float:
	var lowest_y := _foot_contact_y(visual_root)
	if lowest_y == INF:
		lowest_y = _mesh_bottom_y(visual_root)
	if lowest_y == INF:
		return 0.0
	var offset := ground_y - lowest_y
	visual_root.global_position.y += offset
	return offset


static func _authored_scale(node: Node3D, metadata_key: StringName) -> Vector3:
	if node.has_meta(metadata_key):
		var stored: Variant = node.get_meta(metadata_key)
		if stored is Vector3:
			return stored
	var authored := node.scale
	node.set_meta(metadata_key, authored)
	return authored


static func _foot_contact_y(visual_root: Node3D) -> float:
	var lowest_y := INF
	for node in visual_root.find_children("*", "Skeleton3D", true, false):
		var skeleton := node as Skeleton3D
		if skeleton == null:
			continue
		for bone_index in range(skeleton.get_bone_count()):
			var bone_name := skeleton.get_bone_name(bone_index).to_lower()
			if not (
				bone_name.contains("toe_end")
					or bone_name.contains("toeend")
					or bone_name.contains("toe_base")
					or bone_name.contains("toebase")
					or bone_name.ends_with("foot")
			):
				continue
			var foot_point := skeleton.to_global(
				skeleton.get_bone_global_pose(bone_index).origin
			)
			lowest_y = minf(lowest_y, foot_point.y)
	return lowest_y


static func _mesh_bottom_y(visual_root: Node3D) -> float:
	var lowest_y := INF
	for node in visual_root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		var bounds := mesh_instance.get_aabb()
		for x_position in [bounds.position.x, bounds.end.x]:
			for y_position in [bounds.position.y, bounds.end.y]:
				for z_position in [bounds.position.z, bounds.end.z]:
					lowest_y = minf(
						lowest_y,
						mesh_instance.to_global(
							Vector3(x_position, y_position, z_position)
						).y,
					)
	return lowest_y


static func visual_bounds(visual_root: Node3D) -> AABB:
	var bounds := AABB()
	var has_bounds := false
	for node in visual_root.find_children("*", "Skeleton3D", true, false):
		var skeleton := node as Skeleton3D
		for bone_index in range(skeleton.get_bone_count()):
			var point := skeleton.to_global(
				skeleton.get_bone_global_pose(bone_index).origin
			)
			if has_bounds:
				bounds = bounds.expand(point)
			else:
				bounds = AABB(point, Vector3.ZERO)
				has_bounds = true
	if has_bounds:
		return bounds.grow(0.14)
	for node in visual_root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		var mesh_bounds := mesh_instance.global_transform * mesh_instance.get_aabb()
		if has_bounds:
			bounds = bounds.merge(mesh_bounds)
		else:
			bounds = mesh_bounds
			has_bounds = true
	if has_bounds:
		return bounds.grow(0.14)
	return bounds


static func preview_focus_point(visual_root: Node3D, target: String) -> Vector3:
	var bounds := visual_bounds(visual_root)
	if bounds.size.is_zero_approx():
		return visual_root.global_position + Vector3(0.0, 0.9, 0.0)
	if target == "head":
		return Vector3(
			bounds.get_center().x,
			bounds.end.y - bounds.size.y * 0.12,
			bounds.get_center().z,
		)
	return bounds.get_center()


static func _apply_bone_scales(
	visual_root: Node3D,
	raw_values: Variant,
	raw_bindings: Variant,
) -> void:
	if not raw_values is Dictionary or not raw_bindings is Dictionary:
		return
	var bindings := raw_bindings as Dictionary
	for node in visual_root.find_children("*", "Skeleton3D", true, false):
		var skeleton := node as Skeleton3D
		if skeleton == null:
			continue
		for control_name: String in bindings:
			if control_name == "HeadScale" or control_name == "NeckLength":
				continue
			if not (raw_values as Dictionary).has(control_name):
				continue
			var control: Variant = bindings[control_name]
			if not control is Dictionary:
				continue
			var factor := clampf(
				float((raw_values as Dictionary).get(control_name, 1.0)),
				0.5,
				1.5,
			)
			var pose_scale := (
				Vector3.ONE * factor
				if String((control as Dictionary).get("mode", "")) == "uniform"
				else Vector3(1.0, factor, 1.0)
			)
			for bone_name: String in _string_array((control as Dictionary).get("bones", [])):
				var bone_index := skeleton.find_bone(bone_name)
				if bone_index >= 0:
					skeleton.set_bone_pose_scale(bone_index, pose_scale)
		_apply_neck_and_head_scales(skeleton, raw_values as Dictionary, bindings)


static func _apply_neck_and_head_scales(
	skeleton: Skeleton3D,
	raw_values: Dictionary,
	bindings: Dictionary,
) -> void:
	if not raw_values.has("NeckLength") and not raw_values.has("HeadScale"):
		return
	var neck_factor := clampf(float(raw_values.get("NeckLength", 1.0)), 0.5, 1.5)
	var head_factor := clampf(float(raw_values.get("HeadScale", 1.0)), 0.5, 1.5)
	var neck_control: Variant = bindings.get("NeckLength", {})
	if neck_control is Dictionary and raw_values.has("NeckLength"):
		for bone_name: String in _string_array((neck_control as Dictionary).get("bones", [])):
			var neck_index := skeleton.find_bone(bone_name)
			if neck_index >= 0:
				skeleton.set_bone_pose_scale(neck_index, Vector3(1.0, neck_factor, 1.0))
	var head_control: Variant = bindings.get("HeadScale", {})
	if head_control is Dictionary and raw_values.has("HeadScale"):
		for bone_name: String in _string_array((head_control as Dictionary).get("bones", [])):
			var head_index := skeleton.find_bone(bone_name)
			if head_index >= 0:
				# Neck scale is inherited by Head; cancel it on the local length axis.
				skeleton.set_bone_pose_scale(
					head_index,
					Vector3(head_factor, head_factor / neck_factor, head_factor),
				)


static func _apply_blend_shapes(
	visual_root: Node3D,
	raw_values: Variant,
	raw_bindings: Variant,
) -> void:
	if not raw_values is Dictionary or not raw_bindings is Dictionary:
		return
	var bindings := raw_bindings as Dictionary
	for node in visual_root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		for semantic_name: Variant in (raw_values as Dictionary):
			var binding: Variant = bindings.get(String(semantic_name), {})
			var shape_names := [String(semantic_name)]
			if binding is Dictionary:
				var configured_names := _string_array((binding as Dictionary).get("shapes", []))
				if not configured_names.is_empty():
					shape_names = configured_names
			for shape_name: String in shape_names:
				if mesh_instance.find_blend_shape_by_name(StringName(shape_name)) < 0:
					continue
				mesh_instance.set(
					"blend_shapes/%s" % shape_name,
					clampf(float((raw_values as Dictionary)[semantic_name]), 0.0, 1.0),
				)


static func _build_appearance_shader_code() -> String:
	var source := String(REGION_DEBUG_SHADER_CODE)
	var debug_render_mode := (
		"render_mode unshaded, cull_disabled, blend_mix, depth_draw_never;"
	)
	if not source.contains(debug_render_mode):
		push_error("ActorAppearance region shader render mode changed unexpectedly")
		return ""
	source = source.replace(
		debug_render_mode,
		"render_mode unshaded, cull_disabled, depth_draw_opaque;",
	)
	var uniform_anchor := "uniform vec3 appearance_region_coordinate_scale = vec3(1.0);"
	var composition_uniforms := """
uniform vec4 appearance_base_target_color : source_color = vec4(1.0);
uniform vec4 appearance_source_fur_anchor : source_color = vec4(1.0);
uniform float appearance_fur_distance_start = 0.16;
uniform float appearance_fur_distance_end = 0.82;
uniform float appearance_region_mid_luma = 0.62;
uniform int appearance_accent_region_0 = -1;
uniform vec4 appearance_accent_color_0 : source_color = vec4(1.0);
uniform float appearance_accent_intensity_0 = 0.0;
uniform int appearance_accent_region_1 = -1;
uniform vec4 appearance_accent_color_1 : source_color = vec4(1.0);
uniform float appearance_accent_intensity_1 = 0.0;
uniform int appearance_marking_id = 0;
uniform int appearance_marking_placement = 0;
uniform vec4 appearance_marking_zone = vec4(0.0);
uniform vec4 appearance_marking_color : source_color = vec4(1.0);
uniform float appearance_marking_scale = 0.90;
uniform float appearance_marking_intensity = 0.90;
"""
	if not source.contains(uniform_anchor):
		push_error("ActorAppearance region shader uniform anchor changed unexpectedly")
		return ""
	source = source.replace(
		uniform_anchor,
		"%s\n%s" % [uniform_anchor, composition_uniforms],
	)
	var fragment_start := source.rfind("\nvoid fragment() {")
	if fragment_start < 0:
		push_error("ActorAppearance region shader fragment was not found")
		return ""
	return source.substr(0, fragment_start) + APPEARANCE_SHADER_SUFFIX


static func _apply_material_parameters(
	visual_root: Node3D,
	raw_values: Variant,
	raw_bindings: Variant,
	species_id: String,
) -> void:
	if (
		not raw_values is Dictionary
		or (raw_values as Dictionary).is_empty()
		or not raw_bindings is Dictionary
		or not SOURCE_FUR_ANCHORS.has(species_id)
	):
		return
	var values := raw_values as Dictionary
	var appearance_bindings := raw_bindings as Dictionary
	var material_bindings: Variant = appearance_bindings.get("material_parameters", {})
	if not material_bindings is Dictionary:
		return
	var bindings := material_bindings as Dictionary
	var palette_values := _binding_values(bindings, "palette_id")
	var base_color_id := String(
		values.get("primary_color_id", values.get("palette_id", ""))
	)
	var base_color_value: Variant = _color_value(palette_values.get(base_color_id))
	if base_color_value == null:
		push_warning("Appearance palette color is missing: %s/%s" % [species_id, base_color_id])
		return
	var base_color := base_color_value as Color

	var region_ids: Array[int] = [-1, -1]
	var region_colors: Array[Color] = [base_color, base_color]
	var region_intensities: Array[float] = [0.0, 0.0]
	var seen_regions := {}
	for slot in range(MAX_REGION_ACCENTS):
		var region_key := "region_%d_id" % slot
		var mapped_region: Variant = _binding_values(bindings, region_key).get(
			String(values.get(region_key, "none"))
		)
		if not (mapped_region is int or mapped_region is float):
			continue
		var region_id := int(mapped_region)
		if region_id not in COLORABLE_REGION_IDS or seen_regions.has(region_id):
			continue
		var color_id := String(values.get("region_%d_color_id" % slot, base_color_id))
		var color_value: Variant = _color_value(palette_values.get(color_id))
		if color_value == null:
			continue
		region_ids[slot] = region_id
		region_colors[slot] = color_value as Color
		region_intensities[slot] = clampf(
			float(values.get("region_%d_intensity" % slot, 0.0)),
			0.0,
			1.0,
		)
		seen_regions[region_id] = true
	var third_region: Variant = _binding_values(bindings, "region_2_id").get(
		String(values.get("region_2_id", "none"))
	)
	if (third_region is int or third_region is float) and int(third_region) >= 0:
		push_warning("Appearance accepts at most two region accents; region_2 was ignored")

	var marking_id := _mapped_int(
		bindings,
		"marking_id",
		String(values.get("marking_id", "none")),
		0,
	)
	var marking_placement := _mapped_int(
		bindings,
		"marking_placement",
		String(values.get("marking_placement", "none")),
		0,
	)
	if not _valid_marking_placement(marking_id, marking_placement):
		push_warning(
			"Appearance marking placement is unsafe and was disabled: %d/%d"
			% [marking_id, marking_placement]
		)
		marking_id = 0
		marking_placement = 0
	var marking_color_id := String(values.get("marking_color_id", base_color_id))
	var marking_color_value: Variant = _color_value(palette_values.get(marking_color_id))
	var marking_color := (
		marking_color_value as Color
		if marking_color_value != null
		else base_color
	)
	var marking_zones: Variant = appearance_bindings.get("marking_zones", {})
	var zone_value: Variant = null
	if marking_zones is Dictionary:
		zone_value = (marking_zones as Dictionary).get(
			String(values.get("marking_placement", "none")),
			[0.0, 0.0, 0.0, 0.0],
		)
	var marking_zone := _vector4_value(zone_value)
	var marking_scale := clampf(float(values.get("marking_scale", 0.9)), 0.5, 1.25)
	var marking_intensity := clampf(
		float(values.get("marking_intensity", 0.9)),
		0.0,
		1.0,
	)

	var shader_code := _build_appearance_shader_code()
	if shader_code.is_empty():
		return
	var shader := Shader.new()
	shader.code = shader_code
	for node in visual_root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		for surface_index in range(mesh_instance.mesh.get_surface_count()):
			var source_material := _source_material(mesh_instance, surface_index)
			if source_material == null:
				continue
			var source_texture := _source_texture(source_material)
			if source_texture == null:
				continue
			var material := ShaderMaterial.new()
			material.shader = shader
			material.set_shader_parameter(
				"appearance_species_id",
				0 if species_id == "dog" else 1,
			)
			material.set_shader_parameter(
				"appearance_region_coordinate_scale",
				visual_root.scale,
			)
			material.set_shader_parameter(
				"appearance_region_source_texture",
				source_texture,
			)
			material.set_shader_parameter("use_appearance_region_source_texture", true)
			material.set_shader_parameter("appearance_base_target_color", base_color)
			material.set_shader_parameter(
				"appearance_source_fur_anchor",
				SOURCE_FUR_ANCHORS[species_id],
			)
			material.set_shader_parameter(
				"appearance_fur_distance_start",
				float(FUR_DISTANCE_START[species_id]),
			)
			material.set_shader_parameter(
				"appearance_fur_distance_end",
				float(FUR_DISTANCE_END[species_id]),
			)
			material.set_shader_parameter(
				"appearance_region_mid_luma",
				float(REGION_MID_LUMA[species_id]),
			)
			for slot in range(MAX_REGION_ACCENTS):
				material.set_shader_parameter(
					"appearance_accent_region_%d" % slot,
					region_ids[slot],
				)
				material.set_shader_parameter(
					"appearance_accent_color_%d" % slot,
					region_colors[slot],
				)
				material.set_shader_parameter(
					"appearance_accent_intensity_%d" % slot,
					region_intensities[slot],
				)
			material.set_shader_parameter("appearance_marking_id", marking_id)
			material.set_shader_parameter(
				"appearance_marking_placement",
				marking_placement,
			)
			material.set_shader_parameter("appearance_marking_zone", marking_zone)
			material.set_shader_parameter("appearance_marking_color", marking_color)
			material.set_shader_parameter("appearance_marking_scale", marking_scale)
			material.set_shader_parameter(
				"appearance_marking_intensity",
				marking_intensity,
			)
			mesh_instance.set_surface_override_material(surface_index, material)


static func _binding_values(bindings: Dictionary, semantic_name: String) -> Dictionary:
	var binding: Variant = bindings.get(semantic_name, {})
	if not binding is Dictionary:
		return {}
	var values: Variant = (binding as Dictionary).get("values", {})
	return values as Dictionary if values is Dictionary else {}


static func _mapped_int(
	bindings: Dictionary,
	semantic_name: String,
	value: String,
	fallback: int,
) -> int:
	var mapped: Variant = _binding_values(bindings, semantic_name).get(value)
	return int(mapped) if mapped is int or mapped is float else fallback


static func _valid_marking_placement(marking_id: int, placement: int) -> bool:
	if marking_id == 0:
		return placement == 0
	if marking_id >= 1 and marking_id <= 11:
		return placement in [1, 2, 3]
	if marking_id in [12, 13, 15]:
		return placement == 4
	if marking_id == 14:
		return placement in [5, 6]
	return false


static func _source_material(
	mesh_instance: MeshInstance3D,
	surface_index: int,
) -> BaseMaterial3D:
	# The imported actor scenes use active surface materials. Prefer the same
	# resolved material Godot renders (including per-instance overrides) before
	# falling back to the mesh resource's authored material.
	var material: Material = mesh_instance.get_active_material(surface_index)
	if material is BaseMaterial3D:
		return material as BaseMaterial3D
	material = mesh_instance.mesh.surface_get_material(surface_index)
	return material as BaseMaterial3D if material is BaseMaterial3D else null


static func _source_texture(material: BaseMaterial3D) -> Texture2D:
	if material.emission_texture != null:
		return material.emission_texture
	return material.albedo_texture


static func _color_value(value: Variant) -> Variant:
	if value is Array and (value as Array).size() >= 3:
		var components := value as Array
		return Color(
			float(components[0]),
			float(components[1]),
			float(components[2]),
			float(components[3]) if components.size() > 3 else 1.0,
		)
	return null


static func _vector4_value(value: Variant) -> Vector4:
	if value is Array and (value as Array).size() == 4:
		var components := value as Array
		return Vector4(
			float(components[0]),
			float(components[1]),
			float(components[2]),
			float(components[3]),
		)
	return Vector4.ZERO


static func _string_array(value: Variant) -> Array[String]:
	var result: Array[String] = []
	if not value is Array:
		return result
	for item: Variant in value as Array:
		if item is String:
			result.append(item as String)
	return result


static func _appearance_scale(value: Variant, named_values: Dictionary) -> float:
	if value is float or value is int:
		return float(value)
	return float(named_values.get(String(value), 1.0))
