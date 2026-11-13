extends RefCounted
## Presentation only: smooth pressure tracks and independent light colours.
const PERIOD := 80.0
const ICE := Color(0.18,0.65,1.0)
const AQUA := Color(0.08,0.95,0.68)
const VIOLET := Color(0.50,0.12,1.0)
const PINK := Color(1.0,0.12,0.46)
const GOLD := Color(1.0,0.62,0.18)
const WARM := Color(1.0,0.84,0.45)
const FLOWER := [Vector2(0,3.3),Vector2(16,4.6),Vector2(28,4.6),Vector2(32,0),Vector2(54,0),Vector2(60,6),Vector2(64,6),Vector2(66,5.4),Vector2(80,3.3)]
const PLUME := [Vector2(0,0),Vector2(32,0),Vector2(40,4.6),Vector2(44,6),Vector2(48,6),Vector2(50,5.3),Vector2(54,0),Vector2(80,0)]

static func track(t: float,keys: Array) -> float:
 for i in range(1,keys.size()):
  if t<=keys[i].x:
   return lerpf(keys[i-1].y,keys[i].y,smoothstep(keys[i-1].x,keys[i].x,t))
 return keys[-1].y

static func sample(seconds: float) -> Array[Dictionary]:
 var t:=fposmod(seconds,PERIOD)
 var flower_height:=track(t,FLOWER)
 var main_height:=track(t,PLUME)
 # Gentle motion between pressure landmarks, with exact six-metre peak limits.
 flower_height=clampf(flower_height+0.15*sin(TAU*t/4.0)*minf(flower_height,1.0),0.0,6.0)
 main_height=clampf(main_height+0.12*sin(TAU*t/4.0)*minf(main_height,1.0),0.0,6.0)
 var bloom:=smoothstep(54.0,60.0,t)*(1.0-smoothstep(66.0,80.0,t))
 var main_peak:=smoothstep(40.0,44.0,t)*(1.0-smoothstep(50.0,54.0,t))
 var inward:=smoothstep(30.0,34.0,t)*(1.0-smoothstep(50.0,54.0,t))
 var turning:=exp(-pow((t-32.0)/1.5,2.0))+exp(-pow((t-52.0)/1.5,2.0))
 var flower_colors:=PackedColorArray()
 for i in range(8):
  var travel:=0.5+0.5*sin(TAU*t/8.0-float(i)*TAU/8.0)
  var pair:=0.5+0.5*sin(TAU*t/8.0-float(i%4)*PI/2.0)
  var color:=ICE.lerp(AQUA,0.2+0.4*travel)
  color=color.lerp(ICE.lerp(VIOLET,travel),smoothstep(16.0,28.0,t))
  color=color.lerp(PINK.lerp(ICE,pair),smoothstep(54.0,60.0,t))
  color=color.lerp(VIOLET.lerp(ICE,pair),smoothstep(64.0,68.0,t))
  color=color.lerp(ICE.lerp(AQUA,0.2+0.4*travel),smoothstep(68.0,80.0,t))
  flower_colors.append(color)
 var main_color:=GOLD.lerp(WARM,main_peak)
 var result: Array[Dictionary]=[]
 result.append({"height":main_height,"color":main_color,"energy":(1.4+0.35*main_peak)*clampf(main_height/0.5,0.0,1.0),"level":main_height/6.0})
 for i in range(8):
  var wave:=0.5+0.5*sin(TAU*t/4.0-float(i)*0.35)
  var alternate:=0.5+0.5*sin(TAU*t/4.0+float(i%2)*PI)
  var pair:=0.5+0.5*sin(TAU*t/8.0-float(i%4)*PI/2.0)
  var height:=lerpf(0.7+0.4*wave,0.85+0.7*alternate,smoothstep(16.0,20.0,t))
  height=lerpf(height,1.0+0.7*pair,bloom)
  height=lerpf(height,0.7+0.4*wave,smoothstep(66.0,80.0,t))
  height=lerpf(height,2.6+0.8*main_peak,inward)*(1.0-0.85*turning)
  var color:=ICE.lerp(AQUA,wave*0.7).lerp(VIOLET.lerp(ICE,pair),bloom)
  color=color.lerp(ICE.lerp(GOLD,alternate),main_peak*0.7)
  result.append({"height":height,"color":color,"energy":1.4+0.35*(height-0.6)/1.2,"level":(height-0.6)/1.2,"inward":inward})
 var flower_energy:float=(1.4+0.25*bloom)*clampf(flower_height/0.5,0.0,1.0)
 var flower_heights:=PackedFloat32Array()
 var flower_reaches:=PackedFloat32Array()
 for i in range(8):
  flower_heights.append(flower_height)
  flower_reaches.append(lerpf(2.1,3.2,smoothstep(3.0,6.0,flower_height)))
 result[0]["flower_heights"]=flower_heights
 result[0]["flower_reaches"]=flower_reaches
 result[0]["flower_height"]=flower_height
 result[0]["flower_reach"]=lerpf(2.1,3.2,smoothstep(3.0,6.0,flower_height))
 result[0]["flower_colors"]=flower_colors
 result[0]["flower_energy"]=flower_energy
 result[0]["climax"]=maxf(bloom,main_peak)
 var average:=Color(0,0,0,1)
 for color: Color in flower_colors:
  average.r+=color.r/8.0;average.g+=color.g/8.0;average.b+=color.b/8.0
 result[0]["light_color"]=average.lerp(main_color,float(result[0].energy)/maxf(0.001,flower_energy+float(result[0].energy)))
 return result
