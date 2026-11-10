shader_type spatial;
// Feathered light cards retain their texture alpha and translucent rendering.
render_mode blend_mix, depth_draw_never, cull_disabled, diffuse_lambert;
#include "res://nest/estate/estate_arrival_surface.gdshaderinc"
