shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, shadows_disabled;
uniform float level=0.0;
uniform float seconds=0.0;
uniform bool core=false;
uniform bool uplink=false;
uniform bool downlink=false;
uniform bool front=false;
uniform float rise=0.0;
uniform float column_height=1.0;
uniform float bottom=0.0;
uniform float span=1.0;
uniform float color_phase=0.0;
varying float local_height;
void vertex(){ local_height=VERTEX.y; }
vec3 energy_color(float p){
	float t=fract(p)*3.0;
	vec3 cyan=vec3(0.03,0.72,1.0), blue=vec3(0.06,0.24,1.0), violet=vec3(0.55,0.12,1.0);
	if(t<1.0){return mix(cyan,blue,smoothstep(0.0,1.0,t));}
	if(t<2.0){return mix(blue,violet,smoothstep(0.0,1.0,t-1.0));}
	return mix(violet,cyan,smoothstep(0.0,1.0,t-2.0));
}
void fragment(){
	float packet=pow(0.5+0.5*cos(6.2831853*(UV.x*3.0-seconds*1.8)),6.0);
	float edge=core ? pow(1.0-abs(dot(normalize(NORMAL),normalize(VIEW))),1.5) : 1.0;
	float h=(local_height-bottom)/max(span,0.01);
	ALBEDO=energy_color(h*1.6+UV.x*0.3-seconds*0.16+color_phase);
	EMISSION=ALBEDO*0.8;
	float from_bottom=(local_height+column_height*0.5)/column_height;
	float from_top=1.0-from_bottom;
	float formed=uplink ? 1.0-smoothstep(rise-0.08,rise,from_bottom) : (downlink ? 1.0-smoothstep(rise-0.08,rise,from_top) : 1.0);
	float leading=downlink ? exp(-pow((from_top-rise)/0.055,2.0)) : 0.0;
	float opacity=front ? 0.22+packet*0.15 : (core ? 0.12+edge*0.22 : 0.08+packet*0.18);
	ALPHA=level*formed*(opacity+leading*0.22);
}
