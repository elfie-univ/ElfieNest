shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_disabled, diffuse_lambert;
uniform float show_time = 0.0;
uniform int impact_count = 17;
uniform float ring_radius = 4.0;
uniform float start_angle = 0.3926990817;
uniform float heights[9];
uniform float inwards[9];
uniform float inward_reach = 3.3;
uniform float flower_heights[8];
uniform float flower_reaches[8];
uniform vec4 flower_colors[8];
uniform vec4 colors[9];
uniform vec4 impacts[17];
uniform float night_strength = 0.0;
uniform vec3 source_center;
uniform float source_scale = 1.0;
varying vec3 droplet_color;
varying float pressure;
void vertex() {
 int group = INSTANCE_ID%5==0 ? 0 : 1+INSTANCE_ID%16;
 float scatter_angle=INSTANCE_CUSTOM.z*6.2831853;
 vec2 scatter=vec2(cos(scatter_angle),sin(scatter_angle));
 float t=fract(show_time*(0.6+INSTANCE_CUSTOM.w*0.2)+INSTANCE_CUSTOM.y);
 int nozzle=min(group,8);
 float height=group>8 ? flower_heights[group-9] : heights[nozzle];
 droplet_color=group>8 ? flower_colors[group-9].rgb : colors[nozzle].rgb;
 vec3 path=vec3(0.0);
 bool splash=(INSTANCE_ID/17)%4==0;
 if (splash) {
  vec4 landing=impacts[group];
  float age=fract(show_time*2.0+INSTANCE_CUSTOM.y);
  path.xz=landing.xy+scatter*landing.z*(0.3+age*0.8);
  path.y=0.035+4.0*(0.10+INSTANCE_CUSTOM.w*0.20)*age*(1.0-age);
 } else if (group>8) {
  float angle=float(group-9)*6.2831853/8.0;
  float flower_reach=flower_reaches[group-9];
  path=vec3(cos(angle)*flower_reach*t,4.0*height*t*(1.0-t),sin(angle)*flower_reach*t);
  path.xz+=scatter*(0.015+0.055*t);
 } else {
  float angle=start_angle+float(nozzle-1)*6.2831853/8.0;
  vec2 direction=vec2(cos(angle),sin(angle));
  vec2 origin=nozzle==0 ? vec2(0.0) : direction*ring_radius;
  float y=1.0-t*t;
  float width=(nozzle==0 ? 0.48 : 0.23)*(0.15+0.85*(1.0-y));
  vec3 falling=vec3(origin.x+scatter.x*width,height*y,origin.y+scatter.y*width);
  vec3 arch=vec3(origin.x-direction.x*inward_reach*t,4.0*height*t*(1.0-t),origin.y-direction.y*inward_reach*t);
  arch.xz+=scatter*0.05;
  path=nozzle==0 ? falling : mix(falling,arch,inwards[nozzle]);
 }
 pressure=clamp(height/0.5,0.0,1.0);
 vec3 shape=(VERTEX-source_center)*source_scale*(0.65+INSTANCE_CUSTOM.w*0.65);
 shape.y*=splash ? 1.0 : 2.8;
 VERTEX=shape+path;
}
void fragment() {
 ALBEDO=vec3(0.88,0.94,0.97);
 ROUGHNESS=0.48;
 ALPHA=0.86*pressure;
 EMISSION=(vec3(0.22)+droplet_color*night_strength*0.85)*pressure;
}
