shader_type spatial;
// Closed apparatus surfaces write depth; rear triangles cannot cover the top.
render_mode depth_draw_opaque, cull_disabled, diffuse_lambert;
#define ARRIVAL_OPAQUE
#include "res://nest/estate/estate_arrival_surface.gdshaderinc"
