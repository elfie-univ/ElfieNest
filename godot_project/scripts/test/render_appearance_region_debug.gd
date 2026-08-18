extends SceneTree

## Phase 3 region-discovery preview.
##
## This is an experiment/inspection harness, not a production appearance
## material. It renders the original GLB and a 3D local-space region map from
## the same mesh at three camera angles. The region IDs are intentionally
## semantic and coarse: the next step is to approve/refine their boundaries
## before any color combinations are wired into runtime.
##
## Saved review baseline: round-27-disjoint-head-regions (2026-08-17).
## Future boundary changes must create a new round and must not silently
## overwrite the saved baseline evidence.

const DOG_SCENE := preload("res://characters/dog/dog.tscn")
const FOX_SCENE := preload("res://characters/fox/fox.tscn")
const IMAGE_SIZE := Vector2i(512, 512)
const BACKGROUND := Color("707079")
const REGION_BACKGROUND := Color("2a2a31")
const DEFAULT_OUTPUT_DIR := "/private/tmp/elfienest-appearance-reference/phase-3"

const ANGLES: Array[Dictionary] = [
	{"id": "front", "position": Vector3(0.0, 0.96, 3.85)},
	{"id": "three_quarter", "position": Vector3(2.55, 1.00, 3.05)},
	{"id": "side", "position": Vector3(3.85, 0.98, 0.0)},
	{"id": "top", "position": Vector3(0.0, 4.10, 0.0), "up": Vector3(0.0, 0.0, -1.0)},
]

const REGION_KEYS: Array[String] = [
	"head_tuft",
	"forehead_mark_zone",
	"ear_pair",
	"ear_tip_pair",
	"cheek_fluff",
	"chest_tuft",
	"belly_center",
	"forearm_paw_pair",
	"elbow_cuff_pair",
	"lower_leg_foot_pair",
	"knee_cuff_pair",
	"tail_tip",
	"tail_underside",
]

const REGION_LABELS: Dictionary = {
	"head_tuft": "头顶毛",
	"forehead_mark_zone": "额头标记安全区",
	"ear_pair": "耳朵主体的外侧/背侧毛面；狗取耳瓣，狐狸取耳朵外侧与背侧，狐狸耳内白毛保持保护。",
	"ear_tip_pair": "耳尖（狗：下垂耳瓣最下端；狐狸：立耳最上端）",
	"cheek_fluff": "脸颊/嘴边毛",
	"chest_tuft": "胸口毛",
	"belly_center": "腹部中心",
	"forearm_paw_pair": "前臂/手",
	"elbow_cuff_pair": "肘部环",
	"lower_leg_foot_pair": "小腿/脚",
	"knee_cuff_pair": "膝部环",
	"tail_tip": "尾尖",
	"tail_underside": "尾巴下侧",
}

# Review notes for product/manual review. These describe the intended meaning
# of each candidate region; they are not a pre-drawn answer mask.
const REGION_DESCRIPTIONS: Dictionary = {
	"head_tuft": "头顶正中向上突出的单撮毛；只取这撮可见突起，不取周围头顶毛帽。",
	"forehead_mark_zone": "两眉之间、眼睛上方的额头中心安全区；仅供后续局部符号使用。",
	"ear_pair": "耳朵主体的外侧/背侧毛面；狗取耳瓣，狐狸取耳朵外侧与背侧，狐狸耳内白毛保持保护。",
	"ear_tip_pair": "狗只取左右下垂耳瓣的最下端；狐狸只取立耳最上方/最外端的小尖，不包含整只耳朵。",
	"cheek_fluff": "眼睛下方、鼻子两侧的脸颊蓬毛；沿原始脸颊毛束边界。",
	"chest_tuft": "你圈出的上胸心形毛束；只到心形下尖，不能吞进长条腹毛。",
	"belly_center": "胸口心形毛束下方的腹部中央毛面；不包含胸口和腿根。",
	"forearm_paw_pair": "左右前臂到手掌和手指末端的毛发；不包含肩部、上臂主体和肘部过渡环。",
	"elbow_cuff_pair": "左右前臂靠近肘部的一圈过渡毛；不延伸到整条手臂。",
	"lower_leg_foot_pair": "左右小腿到脚掌、脚趾末端的毛发；不包含大腿主体和膝部过渡环。",
	"knee_cuff_pair": "左右膝部附近的一圈过渡毛；不扩展到整条大腿。",
	"tail_tip": "尾巴最末端的尖部毛发；沿尾巴实际末端，不把整条尾巴染色。",
	"tail_underside": "尾巴下缘或下侧的毛面；不包含尾尖，也不串到身体。",
}

const REGION_EXCLUSIONS: Dictionary = {
	"head_tuft": "周围头顶、额头、眉毛、眼睛",
	"forehead_mark_zone": "眼睛、眉毛、鼻子、嘴巴和头顶小撮",
	"ear_pair": "耳尖、狐狸耳内白毛、眼睛和脸颊",
	"ear_tip_pair": "耳朵主体、眼睛和背景",
	"cheek_fluff": "眼睛、鼻子、嘴巴和额头",
	"chest_tuft": "下腹、肚脐、前臂和脸部",
	"belly_center": "胸口心形区、腿根和尾巴",
	"forearm_paw_pair": "肘部环、身体和背景",
	"elbow_cuff_pair": "手掌、肩部和身体",
	"lower_leg_foot_pair": "膝部环、大腿和背景",
	"knee_cuff_pair": "小腿、脚掌和大腿主体",
	"tail_tip": "尾巴主体、尾巴下侧和身体",
	"tail_underside": "尾尖、尾巴上缘和身体",
}

const REGION_COLORS: Array[Color] = [
	Color("00e5ff"),
	Color("d500f9"),
	Color("ffe600"),
	Color("76ff03"),
	Color("00c853"),
	Color("ff00aa"),
	Color("2962ff"),
	Color("7c4dff"),
	Color("ff1744"),
	Color("ff4081"),
	Color("00b8d4"),
	Color("c6ff00"),
	Color("37474f"),
]

# A deliberately coordinated, high-contrast test palette. It is only used to
# judge whether a candidate region is continuous and visually readable; it is
# not a product palette.
const PREVIEW_COLORS: Array[Color] = [
	Color("7d4938"),
	Color("b66a3c"),
	Color("a45a36"),
	Color("60352a"),
	Color("c68f61"),
	Color("d97266"),
	Color("ead2a8"),
	Color("6c3d32"),
	Color("8d5a44"),
	Color("4f302b"),
	Color("6d4438"),
	Color("ead2a8"),
	Color("9b6c50"),
]

const REGION_SHADER_CODE := """
shader_type spatial;
render_mode unshaded, cull_disabled;

uniform int species_id = 0;
uniform int debug_mode = 0;
uniform int selected_region = -1;
uniform bool color_preview = false;
uniform bool overlay_mode = false;
uniform sampler2D source_texture : source_color;
uniform bool use_source_texture = false;
uniform vec4 preview_base_color : source_color = vec4(1.0);
uniform vec4 preview_0 : source_color = vec4(1.0);
uniform vec4 preview_1 : source_color = vec4(1.0);
uniform vec4 preview_2 : source_color = vec4(1.0);
uniform vec4 preview_3 : source_color = vec4(1.0);
uniform vec4 preview_4 : source_color = vec4(1.0);
uniform vec4 preview_5 : source_color = vec4(1.0);
uniform vec4 preview_6 : source_color = vec4(1.0);
uniform vec4 preview_7 : source_color = vec4(1.0);
uniform vec4 preview_8 : source_color = vec4(1.0);
uniform vec4 preview_9 : source_color = vec4(1.0);
uniform vec4 preview_10 : source_color = vec4(1.0);
uniform vec4 preview_11 : source_color = vec4(1.0);
uniform vec4 preview_12 : source_color = vec4(1.0);

varying vec3 region_position;
varying vec3 region_normal;
varying vec2 region_uv;
varying float region_tail_bone;
varying float region_leg_bone;
varying float region_lower_leg_bone;
varying float region_arm_bone;
varying float region_forearm_bone;
varying float region_head_bone;
varying float region_head_top_bone;

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
    // Imported GLBs keep armature coordinates in centimetres while the
    // Armature node carries the 0.01 scene scale. VERTEX alone is therefore
    // not the same coordinate system as the visible actor. Use the evaluated
    // model transform so region thresholds are expressed in scene metres.
    region_position = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
    region_normal = NORMAL;
    region_uv = UV;
    uvec4 bone_indices = BONE_INDICES;
    vec4 bone_weights = BONE_WEIGHTS;
    // The imported skeletons do not have the same length: the dog has 35
    // bones (tail=33, head/head-top=23/24), while the fox has 42 (tail=41,
    // head/head-top=27/28). Keep the semantic regions species-specific and
    // use exact arm ranges so neck/head/tail bones cannot leak into the arms.
    region_leg_bone = joint_weight_range(bone_indices, bone_weights, 1u, 10u);
	region_lower_leg_bone = joint_weight_range(bone_indices, bone_weights, 2u, 5u)
		+ joint_weight_range(bone_indices, bone_weights, 7u, 10u);
	if (species_id == 0) {
		region_tail_bone = joint_weight(bone_indices, bone_weights, 33u);
		region_arm_bone = joint_weight_range(bone_indices, bone_weights, 14u, 21u)
			+ joint_weight_range(bone_indices, bone_weights, 25u, 32u);
		region_forearm_bone = joint_weight_range(bone_indices, bone_weights, 16u, 21u)
			+ joint_weight_range(bone_indices, bone_weights, 27u, 32u);
		region_head_bone = joint_weight(bone_indices, bone_weights, 23u);
		region_head_top_bone = joint_weight(bone_indices, bone_weights, 24u);
	} else {
		region_tail_bone = joint_weight(bone_indices, bone_weights, 41u);
		region_arm_bone = joint_weight_range(bone_indices, bone_weights, 14u, 25u)
			+ joint_weight_range(bone_indices, bone_weights, 29u, 40u);
		region_forearm_bone = joint_weight_range(bone_indices, bone_weights, 16u, 25u)
			+ joint_weight_range(bone_indices, bone_weights, 31u, 40u);
		region_head_bone = joint_weight(bone_indices, bone_weights, 27u);
		region_head_top_bone = joint_weight(bone_indices, bone_weights, 28u);
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

float front_surface() {
    return smoothstep(-0.02, 0.22, region_position.z)
        * smoothstep(-0.02, 0.20, region_normal.z);
}

float head_tuft() {
	// Product definition: only the small central tuft that protrudes above the
	// crown. The surrounding forehead/crown is intentionally excluded.
	// The fox tuft sits lower and is substantially smaller than the dog's
	// upright crown tuft; sharing the dog's y-band made the fox candidate
	// disappear while the dog candidate captured too much crown.
	float crown = species_id == 1
		? soft_band(region_position.y, 1.63, 1.76, 0.018)
		: soft_band(region_position.y, 1.80, 1.97, 0.020);
	// A normal-only test captured the visible front ridge but had no control over
	// the tuft's front/back footprint in the top view. Use a rounded, tapered
	// depth footprint so the rear half is included without turning the crown
	// into a rectangular stripe.
	float depth_center = species_id == 1 ? 0.45 : 0.25;
	// The first rear-inclusive pass used a half-depth of ~0.4 and became a
	// vertical stripe in the top view. Use a tapered ellipse instead: it keeps
	// the rear half of the actual tuft while excluding the surrounding crown.
	float depth_radius = species_id == 1 ? 0.26 : 0.28;
	float width_radius = species_id == 1 ? 0.12 : 0.085;
	float ellipse_distance =
		pow(region_position.x / width_radius, 2.0)
		+ pow((region_position.z - depth_center) / depth_radius, 2.0);
	float center = 1.0 - smoothstep(0.48, 1.0, ellipse_distance);
	float tuft_bone = max(region_head_top_bone, region_head_bone * 0.65);
	return crown * center * smoothstep(0.05, 0.22, tuft_bone);
}

float forehead_mark_zone() {
	// Only the central forehead gap is allowed: keep it above the eyes and
	// between the brows, never as a full-width forehead strip.
	float forehead = species_id == 1
		? soft_band(region_position.y, 1.52, 1.68, 0.020)
		: soft_band(region_position.y, 1.62, 1.77, 0.020);
	float center = species_id == 1
		? soft_abs_band(region_position.x, 0.14, 0.018)
		: soft_abs_band(region_position.x, 0.105, 0.018);
	float front = species_id == 1
		? smoothstep(0.18, 0.30, region_position.z)
			* smoothstep(0.12, 0.24, region_normal.z)
		: smoothstep(0.22, 0.34, region_position.z)
			* smoothstep(0.16, 0.27, region_normal.z);
	// The mark zone may sit immediately below the tuft, but it must never own
	// the tuft's protruding vertices. Keep the two semantic regions disjoint in
	// both the front and top views.
	float tuft_clear = 1.0 - smoothstep(0.10, 0.34, head_tuft());
	return forehead * center * front * tuft_clear;
}

float source_luminance() {
    if (!use_source_texture) return 0.0;
    return dot(texture(source_texture, region_uv).rgb, vec3(0.299, 0.587, 0.114));
}

float source_chroma() {
    if (!use_source_texture) return 1.0;
    vec3 source = texture(source_texture, region_uv).rgb;
    float high = max(max(source.r, source.g), source.b);
    float low = min(min(source.r, source.g), source.b);
    return high - low;
}

float fox_inner_white_ear() {
    // The fox GLB has the inner ear baked as low-chroma, high-luminance white
    // fur in the source atlas. Use that material evidence only inside the
    // geometric ear band; it prevents the outer-ear candidate from recoloring
    // the protected white inner fur without inventing a screen-space polygon.
    float white = smoothstep(0.62, 0.80, source_luminance());
    float low_chroma = 1.0 - smoothstep(0.05, 0.16, source_chroma());
    return white * low_chroma;
}

float ear_pair() {
    float side = smoothstep(0.255, 0.34, abs(region_position.x));
    float height = soft_band(region_position.y, 1.36, 1.82, 0.035);
    float front = smoothstep(0.0, 0.16, region_position.z)
        * smoothstep(-0.04, 0.12, region_normal.z);
    float surface = species_id == 1
        ? (1.0 - fox_inner_white_ear())
        : front;
    return side * height * surface;
}

float ear_tip_pair() {
	float radius = abs(region_position.x);
	float side = species_id == 0
		? smoothstep(0.31, 0.40, radius)
			* (1.0 - smoothstep(0.58, 0.64, radius))
		: smoothstep(0.27, 0.33, radius)
			* (1.0 - smoothstep(0.45, 0.51, radius));
	// A floppy dog's "tip" is the low hanging end of the ear flap. A fox's
	// tip is the opposite anatomical landmark: the upper point of the upright
	// ear. They must not share a y-band.
	float height = species_id == 0
		? soft_band(region_position.y, 1.10, 1.38, 0.030)
		: soft_band(region_position.y, 1.76, 2.00, 0.030);
	float surface = species_id == 0
		? smoothstep(-0.04, 0.16, region_position.z)
		: smoothstep(-0.04, 0.16, region_position.z);
	return side * height * surface;
}

float cheek_fluff() {
	// The cheek is a side-muzzle mass below the eyes. Bound both the inner
	// edge (identity features) and the outer edge (ear/face boundary).
	float face = species_id == 0
		? soft_band(region_position.y, 1.23, 1.44, 0.025)
		: soft_band(region_position.y, 1.18, 1.43, 0.025);
	float inner_radius = species_id == 1 ? 0.16 : 0.13;
	float outer_radius = species_id == 1 ? 0.36 : 0.30;
	float sides = smoothstep(inner_radius, inner_radius + 0.035, abs(region_position.x))
		* (1.0 - smoothstep(outer_radius - 0.035, outer_radius, abs(region_position.x)));
	float front = species_id == 0
		? smoothstep(0.20, 0.38, region_position.z)
			* smoothstep(0.22, 0.42, region_normal.z)
		: smoothstep(0.12, 0.24, region_position.z)
			* smoothstep(0.10, 0.22, region_normal.z);
	return face * sides * front * smoothstep(0.05, 0.28, region_head_bone);
}

float chest_tuft() {
	// Product definition: the upper, heart-shaped chest tuft only. The long
	// white belly, neck and shoulders must remain outside this region.
	// The previous positive fox offset selected a lower slice of the mesh
	// because the test coordinates are added before the target band is applied.
	// Reduce it so the fox heart moves up to the user's marked upper-chest tuft.
	// Smaller offsets select a slightly higher slice of this mesh. Keep the
	// fox heart above the old lower placement, and nudge the dog up a little
	// as well so both match the product-marked upper-chest tuft.
	float chest_y = region_position.y + (species_id == 1 ? 0.0 : -0.04);
	vec2 point = vec2(region_position.x, chest_y);
	float left_lobe = 1.0 - smoothstep(
		1.0,
		1.0 + 0.06,
		length((point - vec2(-0.065, 0.98)) / vec2(0.085, 0.065))
	);
	float right_lobe = 1.0 - smoothstep(
		1.0,
		1.0 + 0.06,
		length((point - vec2(0.065, 0.98)) / vec2(0.085, 0.065))
	);
	// The pointed lower part is deliberately below the lobes, on the torso;
	// the previous 1.25-centred version landed on the muzzle in this mesh.
	float point_progress = smoothstep(0.78, 0.91, chest_y);
	float point_width = mix(0.0, 0.065, point_progress);
	float point_tip = soft_band(chest_y, 0.76, 0.99, 0.020)
		* soft_abs_band(region_position.x, point_width, 0.016);
	float heart = max(max(left_lobe, right_lobe), point_tip);
	return heart * smoothstep(0.06, 0.20, region_position.z)
		* smoothstep(0.14, 0.28, region_normal.z);
}

float belly_center() {
	// The belly is a rounded fur mass, not a rectangular recolor panel. Use a
	// soft ellipse with a slightly pear-shaped width profile so both ends are
	// smooth and the lower edge stops before the leg split.
	float center_y = species_id == 1 ? 0.70 : 0.69;
	float half_height = species_id == 1 ? 0.28 : 0.27;
	float vertical = abs((region_position.y - center_y) / half_height);
	float inside = 1.0 - smoothstep(0.78, 1.0, vertical);
	float bulge = sqrt(max(0.0, 1.0 - min(vertical * vertical, 1.0)));
	float max_width = species_id == 1 ? 0.17 : 0.16;
	float width = mix(0.045, max_width, bulge);
	float center = 1.0 - smoothstep(width, width + 0.025, abs(region_position.x));
	return inside * center
		// Belly is a front-facing area. Requiring a stronger front normal and a
		// tighter body-center band prevents its color from appearing on the tail
		// root in the side/three-quarter views.
		* smoothstep(0.12, 0.28, region_position.z)
		* smoothstep(0.42, 0.56, region_normal.z)
		* (1.0 - smoothstep(0.14, 0.20, abs(region_position.x)));
}

float forearm_paw_pair() {
	// Use only forearm/hand bones. The previous all-arm gate left the upper-arm
	// section and hand as two visible islands once the elbow ring was overlaid.
	// This ownership set follows the limb around the mesh and excludes shoulder
	// and upper-arm bones entirely.
	return smoothstep(0.18, 0.52, region_forearm_bone);
}

float limb_body_clearance() {
	return 1.0;
}

float elbow_cuff_pair() {
	float elbow = soft_band(region_position.y, 0.66, 0.84, 0.035);
	return elbow * smoothstep(0.18, 0.52, region_arm_bone);
}

float lower_leg_foot_pair() {
	// The lower-leg/foot region must wrap around the limb. Bone ownership gives
	// that wrap without selecting the similarly placed tail root.
	float leg = soft_band(region_position.y, -0.04, 0.38, 0.035);
	return leg * smoothstep(0.22, 0.58, region_lower_leg_bone);
}

float knee_cuff_pair() {
	// A small oval cap, slightly below the old band. The leg bone gate removes
	// the hip and tail false positives while allowing the cap to wrap around.
	float center_x = species_id == 1 ? 0.17 : 0.18;
	float dx = abs(abs(region_position.x) - center_x) / 0.12;
	float dy = abs(region_position.y - 0.36) / 0.085;
	float cap = 1.0 - smoothstep(0.72, 1.0, dx * dx + dy * dy);
	return cap * smoothstep(0.18, 0.52, region_leg_bone);
}

float tail_tip() {
	// Both species use the tail bone and radial distance from the body. This
	// follows the raised dog tail as well as the fox's horizontal tail instead
	// of assuming a single z direction.
	float tail_progress = length(vec2(region_position.x, region_position.z));
	float endpoint = species_id == 0
		? smoothstep(0.56, 0.80, tail_progress)
		: smoothstep(0.64, 0.90, tail_progress);
	return endpoint * smoothstep(0.24, 0.66, region_tail_bone);
}

float tail_underside() {
	float tail_progress = length(vec2(region_position.x, region_position.z));
	float not_tip = 1.0 - smoothstep(0.74, 0.92, tail_progress);
	float underside = smoothstep(0.08, 0.32, -region_normal.y);
	return not_tip * underside * smoothstep(0.24, 0.66, region_tail_bone);
}

float region_alpha(int region_id) {
    if (region_id == 0) return head_tuft();
    if (region_id == 1) return forehead_mark_zone();
    if (region_id == 2) return ear_pair();
    if (region_id == 3) return ear_tip_pair();
    if (region_id == 4) return cheek_fluff();
    if (region_id == 5) return chest_tuft();
    if (region_id == 6) return belly_center();
    if (region_id == 7) return forearm_paw_pair();
    if (region_id == 8) return elbow_cuff_pair();
    if (region_id == 9) return lower_leg_foot_pair();
    if (region_id == 10) return knee_cuff_pair();
    if (region_id == 11) return tail_tip();
    if (region_id == 12) return tail_underside();
    return 0.0;
}

int classify_region() {
    // The order deliberately gives the smaller semantic regions priority over
    // their broader parent bands. This makes overlaps visible during review.
    // Tips should own their overlap with the broader ear region in the
    // all-regions plate. The selected-region mode still lets us inspect both.
    if (region_alpha(0) > 0.52) return 0;
    if (region_alpha(1) > 0.52) return 1;
    if (region_alpha(3) > 0.52) return 3;
    if (region_alpha(2) > 0.52) return 2;
    if (region_alpha(4) > 0.52) return 4;
    if (region_alpha(5) > 0.52) return 5;
    if (region_alpha(6) > 0.52) return 6;
    if (region_alpha(8) > 0.52) return 8;
    if (region_alpha(10) > 0.52) return 10;
    if (region_alpha(7) > 0.52) return 7;
    if (region_alpha(9) > 0.52) return 9;
    if (region_alpha(11) > 0.52) return 11;
    if (region_alpha(12) > 0.52) return 12;
    return -1;
}

vec3 region_color(int region_id) {
	if (region_id == 0) return vec3(0.0, 0.898, 1.0);
	if (region_id == 1) return vec3(0.835, 0.0, 0.976);
	if (region_id == 2) return vec3(1.0, 0.902, 0.0);
	if (region_id == 3) return vec3(0.463, 1.0, 0.012);
	if (region_id == 4) return vec3(0.0, 0.784, 0.325);
	if (region_id == 5) return vec3(1.0, 0.0, 0.667);
	if (region_id == 6) return vec3(0.161, 0.384, 1.0);
	if (region_id == 7) return vec3(0.486, 0.302, 1.0);
	if (region_id == 8) return vec3(1.0, 0.090, 0.267);
	if (region_id == 9) return vec3(1.0, 0.251, 0.506);
	if (region_id == 10) return vec3(0.0, 0.722, 0.831);
	if (region_id == 11) return vec3(0.776, 1.0, 0.0);
	if (region_id == 12) return vec3(0.216, 0.278, 0.322);
	return vec3(0.16, 0.16, 0.19);
}

vec3 preview_color(int region_id) {
	if (region_id == 0) return preview_0.rgb;
	if (region_id == 1) return preview_1.rgb;
	if (region_id == 2) return preview_2.rgb;
	if (region_id == 3) return preview_3.rgb;
	if (region_id == 4) return preview_4.rgb;
	if (region_id == 5) return preview_5.rgb;
	if (region_id == 6) return preview_6.rgb;
	if (region_id == 7) return preview_7.rgb;
	if (region_id == 8) return preview_8.rgb;
	if (region_id == 9) return preview_9.rgb;
	if (region_id == 10) return preview_10.rgb;
	if (region_id == 11) return preview_11.rgb;
	if (region_id == 12) return preview_12.rgb;
	return vec3(1.0);
}

float luminance(vec3 color) {
	return dot(color, vec3(0.299, 0.587, 0.114));
}

void fragment() {
	int region_id = classify_region();
	vec3 color = vec3(0.16, 0.16, 0.19);
	float overlay_coverage = 0.0;
	if (overlay_mode) {
		// In per-region review mode the selected region must be evaluated on its
		// own. Routing it through classify_region() hid overlaps behind the chest,
		// elbow, or knee priority and made a correct mask look fragmented.
		int overlay_region = selected_region >= 0 ? selected_region : region_id;
		if (overlay_region >= 0) {
			overlay_coverage = clamp(region_alpha(overlay_region), 0.0, 1.0);
			color = preview_color(overlay_region);
		} else {
			color = vec3(0.0);
		}
	} else if (color_preview) {
		vec3 source = preview_base_color.rgb;
		if (use_source_texture) {
			// The imported source texture is the baked fur response. Match the
			// accepted appearance path and do not multiply it by the imported
			// material's often-black base color.
			source = texture(source_texture, UV).rgb;
		}
		if (luminance(source) < 0.02) {
			source = vec3(0.72);
		}
		int preview_region = region_id;
		if (selected_region >= 0 && preview_region != selected_region) {
			preview_region = -1;
		}
		if (preview_region >= 0) {
			float source_luma = max(luminance(source), 0.001);
			float relative_detail = pow(source_luma / 0.64, 0.78);
			vec3 recolored = clamp(preview_color(preview_region) * relative_detail, vec3(0.0), vec3(1.0));
			color = mix(source, recolored, 0.92);
			// Keep dark identity features from being swallowed by the test tint.
			float dark_feature = 1.0 - smoothstep(0.03, 0.20, source_luma);
			color = mix(color, source, dark_feature * 0.86);
		} else {
			color = source;
		}
	} else if (debug_mode == 2) {
        color = vec3(
            clamp(region_position.x / 1.2 + 0.5, 0.0, 1.0),
            clamp(region_position.y / 1.9, 0.0, 1.0),
            clamp(region_position.z / 1.2 + 0.5, 0.0, 1.0)
        );
    } else if (debug_mode == 0 && region_id >= 0) {
        color = region_color(region_id);
    } else if (debug_mode == 1 && selected_region >= 0) {
        float selected = region_alpha(selected_region);
        color = mix(vec3(0.08, 0.08, 0.10), region_color(selected_region), selected);
	}
	ALBEDO = color;
	ALPHA = overlay_mode ? overlay_coverage * 0.78 : 1.0;
}
"""

var _output_dir := DEFAULT_OUTPUT_DIR
var _heatmap := false
var _selected_region := -1
var _color_preview := false
var _overlay_debug := false
var _region_grid := false


func _init() -> void:
	var configured_output := OS.get_environment("APPEARANCE_REGION_OUTPUT")
	if not configured_output.is_empty():
		_output_dir = configured_output
		_heatmap = not OS.get_environment("APPEARANCE_REGION_HEATMAP").is_empty()
	_color_preview = OS.get_environment("APPEARANCE_REGION_COLOR_PREVIEW") == "1"
	_overlay_debug = OS.get_environment("APPEARANCE_REGION_OVERLAY_DEBUG") == "1"
	_region_grid = OS.get_environment("APPEARANCE_REGION_GRID") == "1"
	var selected_value := OS.get_environment("APPEARANCE_REGION_SELECTED")
	if not selected_value.is_empty():
		_selected_region = int(selected_value)
	call_deferred("_render")


func _render() -> void:
	DirAccess.make_dir_recursive_absolute(_output_dir)
	if _region_grid:
		await _render_region_grids()
		_write_region_catalog()
		_print_region_catalog()
		print("APPEARANCE_REGION_DEBUG_OUTPUT: %s" % _output_dir)
		quit()
		return
	var suffix := _artifact_suffix()
	var dog_plate := await _render_species_plate("dog", DOG_SCENE)
	var fox_plate := await _render_species_plate("fox", FOX_SCENE)
	dog_plate.save_png("%s/dog-region-debug%s.png" % [_output_dir, suffix])
	fox_plate.save_png("%s/fox-region-debug%s.png" % [_output_dir, suffix])
	_join_vertical([dog_plate, fox_plate]).save_png("%s/region-debug-all%s.png" % [_output_dir, suffix])
	_write_region_catalog()
	if _color_preview:
		var dog_color_plate := await _render_species_color_preview_plate("dog", DOG_SCENE)
		var fox_color_plate := await _render_species_color_preview_plate("fox", FOX_SCENE)
		dog_color_plate.save_png("%s/dog-region-color-preview%s.png" % [_output_dir, suffix])
		fox_color_plate.save_png("%s/fox-region-color-preview%s.png" % [_output_dir, suffix])
		_join_vertical([dog_color_plate, fox_color_plate]).save_png("%s/region-color-preview-all%s.png" % [_output_dir, suffix])
	if _overlay_debug:
		var dog_overlay_plate := await _render_species_overlay_debug_plate("dog", DOG_SCENE)
		var fox_overlay_plate := await _render_species_overlay_debug_plate("fox", FOX_SCENE)
		dog_overlay_plate.save_png("%s/dog-region-overlay-debug%s.png" % [_output_dir, suffix])
		fox_overlay_plate.save_png("%s/fox-region-overlay-debug%s.png" % [_output_dir, suffix])
		_join_vertical([dog_overlay_plate, fox_overlay_plate]).save_png("%s/region-overlay-debug-all%s.png" % [_output_dir, suffix])
	_print_region_catalog()
	print("APPEARANCE_REGION_DEBUG_OUTPUT: %s" % _output_dir)
	quit()


func _render_region_grids() -> void:
	var grid_catalog: Dictionary = {
		"schema": "appearance-region-grid.v1",
		"purpose": "每个区域单独使用诊断色渲染四个视角；每一行对应一个区域，便于人工逐区检查串色和漏色。",
		"columns": ["front", "three_quarter", "side", "top"],
		"color_source": "REGION_COLORS",
		"rows": [],
	}
	for index in range(REGION_KEYS.size()):
		var key := REGION_KEYS[index]
		grid_catalog["rows"].append({
			"row": index + 1,
			"id": index,
			"key": key,
			"label_zh": String(REGION_LABELS[key]),
			"color": "#%s" % REGION_COLORS[index].to_html(false),
		})
	for species: Dictionary in [
		{"id": "dog", "scene": DOG_SCENE},
		{"id": "fox", "scene": FOX_SCENE},
	]:
		var rows: Array[Image] = []
		for index in range(REGION_KEYS.size()):
			_selected_region = index
			var row := await _render_species_overlay_debug_plate(species["id"], species["scene"])
			var row_path := "%s/%s-region-%02d-%s-4views.png" % [
				_output_dir,
				species["id"],
				index,
				REGION_KEYS[index],
			]
			row.save_png(row_path)
			rows.append(row)
		var grid_path := "%s/%s-region-grid-4views.png" % [_output_dir, species["id"]]
		_join_vertical(rows).save_png(grid_path)
		grid_catalog["%s_grid" % species["id"]] = grid_path.get_file()
	_selected_region = -1
	var catalog_path := "%s/region-grid-catalog.json" % _output_dir
	var catalog := FileAccess.open(catalog_path, FileAccess.WRITE)
	if catalog != null:
		catalog.store_string(JSON.stringify(grid_catalog, "\t"))
		catalog.close()


func _artifact_suffix() -> String:
	if _selected_region < 0 or _selected_region >= REGION_KEYS.size():
		return ""
	return "-selected-%02d-%s" % [_selected_region, REGION_KEYS[_selected_region]]


func _render_species_plate(species_id: String, scene: PackedScene) -> Image:
	var originals: Array[Image] = []
	var regions: Array[Image] = []
	for angle: Dictionary in ANGLES:
		originals.append(await _render_scene(scene, species_id, angle, 0))
		regions.append(await _render_scene(scene, species_id, angle, 1))
	return _join_vertical([_join_horizontal(originals), _join_horizontal(regions)])


func _render_species_color_preview_plate(species_id: String, scene: PackedScene) -> Image:
	var originals: Array[Image] = []
	var previews: Array[Image] = []
	for angle: Dictionary in ANGLES:
		originals.append(await _render_scene(scene, species_id, angle, 0))
		previews.append(await _render_scene(scene, species_id, angle, 2))
	return _join_vertical([_join_horizontal(originals), _join_horizontal(previews)])


func _render_species_overlay_debug_plate(species_id: String, scene: PackedScene) -> Image:
	var overlays: Array[Image] = []
	for angle: Dictionary in ANGLES:
		overlays.append(await _render_scene(scene, species_id, angle, 3))
	return _join_horizontal(overlays)


func _render_scene(
	scene: PackedScene,
	species_id: String,
	angle: Dictionary,
	render_mode: int,
) -> Image:
	var region_debug := render_mode == 1
	var color_preview := render_mode == 2
	var overlay_debug := render_mode == 3
	var viewport := SubViewport.new()
	viewport.size = IMAGE_SIZE
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	viewport.transparent_bg = false
	root.add_child(viewport)

	var world := Node3D.new()
	viewport.add_child(world)
	var environment := WorldEnvironment.new()
	var environment_resource := Environment.new()
	environment_resource.background_mode = Environment.BG_COLOR
	environment_resource.background_color = REGION_BACKGROUND if region_debug else BACKGROUND
	environment_resource.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment_resource.ambient_light_color = Color.WHITE
	environment_resource.ambient_light_energy = 1.0
	environment.environment = environment_resource
	world.add_child(environment)

	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-28.0, -25.0, 0.0)
	light.light_energy = 1.0
	world.add_child(light)

	var camera := Camera3D.new()
	camera.position = angle["position"]
	camera.fov = 36.0
	world.add_child(camera)
	var camera_up: Vector3 = angle.get("up", Vector3.UP)
	camera.look_at(Vector3(0.0, 0.88, 0.0), camera_up)
	camera.current = true

	var actor := scene.instantiate() as Node3D
	if actor is ElfieActor:
		(actor as ElfieActor).install_shared_animations = false
	world.add_child(actor)
	if region_debug or color_preview:
		_apply_region_material(actor, species_id, color_preview)
	if overlay_debug:
		_apply_region_overlay(actor, species_id, true)

	await process_frame
	await process_frame
	await process_frame
	await process_frame
	var image := viewport.get_texture().get_image()
	viewport.queue_free()
	await process_frame
	return image


func _apply_region_material(actor: Node3D, species_id: String, color_preview: bool = false) -> void:
	if color_preview:
		_apply_region_overlay(actor, species_id)
		return
	var shader := Shader.new()
	shader.code = REGION_SHADER_CODE
	for node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		for surface_index in range(mesh_instance.mesh.get_surface_count()):
			var material := ShaderMaterial.new()
			material.shader = shader
			material.set_shader_parameter("species_id", 0 if species_id == "dog" else 1)
			material.set_shader_parameter("color_preview", color_preview)
			material.set_shader_parameter(
				"debug_mode",
				2 if _heatmap else (1 if _selected_region >= 0 else 0),
			)
			material.set_shader_parameter("selected_region", _selected_region)
			for region_index in range(PREVIEW_COLORS.size()):
				material.set_shader_parameter(
					"preview_%d" % region_index,
					PREVIEW_COLORS[region_index],
				)
			var source_material: Material = mesh_instance.get_active_material(surface_index)
			if source_material is BaseMaterial3D:
				var base_material := source_material as BaseMaterial3D
				material.set_shader_parameter("preview_base_color", base_material.albedo_color)
				var source_texture: Texture2D = base_material.emission_texture
				if source_texture == null:
					source_texture = base_material.albedo_texture
				if source_texture != null:
					material.set_shader_parameter("source_texture", source_texture)
					material.set_shader_parameter("use_source_texture", true)
			mesh_instance.set_surface_override_material(surface_index, material)


func _apply_region_overlay(actor: Node3D, species_id: String, debug_colors: bool = false) -> void:
	var shader := Shader.new()
	shader.code = REGION_SHADER_CODE.replace(
		"render_mode unshaded, cull_disabled;",
		"render_mode unshaded, cull_disabled, blend_mix, depth_draw_never;",
	)
	for node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		var material := ShaderMaterial.new()
		material.shader = shader
		material.set_shader_parameter("species_id", 0 if species_id == "dog" else 1)
		material.set_shader_parameter("color_preview", true)
		material.set_shader_parameter("overlay_mode", true)
		material.set_shader_parameter("selected_region", _selected_region)
		var colors := REGION_COLORS if debug_colors else PREVIEW_COLORS
		for region_index in range(colors.size()):
			material.set_shader_parameter(
				"preview_%d" % region_index,
				colors[region_index],
			)
		var source_material: Material = mesh_instance.get_active_material(0)
		if source_material is BaseMaterial3D:
			var base_material := source_material as BaseMaterial3D
			var source_texture: Texture2D = base_material.emission_texture
			if source_texture == null:
				source_texture = base_material.albedo_texture
			if source_texture != null:
				material.set_shader_parameter("source_texture", source_texture)
				material.set_shader_parameter("use_source_texture", true)
		mesh_instance.material_overlay = material


func _print_region_catalog() -> void:
	for index in range(REGION_KEYS.size()):
		var key := REGION_KEYS[index]
		print(
			"REGION id=%02d key=%s label=%s color=%s target=%s exclude=%s"
			% [
				index,
				key,
				String(REGION_LABELS[key]),
				REGION_COLORS[index].to_html(false),
				String(REGION_DESCRIPTIONS[key]),
				String(REGION_EXCLUSIONS[key]),
			]
		)


func _write_region_catalog() -> void:
	var regions: Array[Dictionary] = []
	for index in range(REGION_KEYS.size()):
		var key := REGION_KEYS[index]
		regions.append({
			"id": index,
			"key": key,
			"label_zh": String(REGION_LABELS[key]),
			"color": "#%s" % REGION_COLORS[index].to_html(false),
			"target": String(REGION_DESCRIPTIONS[key]),
			"exclude": String(REGION_EXCLUSIONS[key]),
		})
	var payload := {
		"schema": "appearance-region-review.v1",
		"purpose": "给视觉模型逐区检查实际 Godot 分色渲染；不是预先给出的答案遮罩。",
		"views": ["front", "three_quarter", "side", "top"],
		"regions": regions,
	}
	var catalog_path := "%s/region-catalog.json" % _output_dir
	var catalog := FileAccess.open(catalog_path, FileAccess.WRITE)
	if catalog == null:
		push_error("Unable to write region catalog: %s" % catalog_path)
		return
	catalog.store_string(JSON.stringify(payload, "\t"))
	catalog.close()


func _join_horizontal(images: Array[Image]) -> Image:
	var output := Image.create(IMAGE_SIZE.x * images.size(), IMAGE_SIZE.y, false, Image.FORMAT_RGBA8)
	for index in range(images.size()):
		output.blit_rect(images[index], Rect2i(Vector2i.ZERO, IMAGE_SIZE), Vector2i(index * IMAGE_SIZE.x, 0))
	return output


func _join_vertical(images: Array[Image]) -> Image:
	var width := 0
	var height := 0
	for image in images:
		width = maxi(width, image.get_width())
		height += image.get_height()
	var output := Image.create(width, height, false, Image.FORMAT_RGBA8)
	var y_offset := 0
	for image in images:
		output.blit_rect(image, Rect2i(Vector2i.ZERO, image.get_size()), Vector2i(0, y_offset))
		y_offset += image.get_height()
	return output
