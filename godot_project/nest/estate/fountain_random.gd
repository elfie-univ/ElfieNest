extends RefCounted
## Seeded ensembles: six centre gestures coordinated with sixteen outer actions.
const FIXED := preload("res://nest/estate/fountain_score.gd")
const PHRASE_SECONDS := 24.0
const ACTIONS := ["breath","alternate","opposite","wave","build","drain","stairs","rotating_stairs","arch_chase","paired_arch","growing_arch","dome","four_and_four","two_and_six","half_and_half","role_exchange"]
const CENTRES := [3,4,2,5,1,3,1,5,0,2,1,1,0,2,0,0]
const SCENES := [4,6,3,1,0,4,0,1,2,3,2,7,5,5,5,5]
const PALETTES := [
 [Color(0.16,0.72,1.0),Color(0.22,0.95,0.72)],
 [Color(0.26,0.55,1.0),Color(0.68,0.25,0.92)],
 [Color(0.25,0.78,1.0),Color(0.95,0.30,0.64)],
 [Color(0.35,0.85,0.92),Color(0.62,0.62,1.0)],
]
var _block := -1
var _seed := -1
var _plans: Array[Dictionary]=[]

func phrase(slot:int,seed_value:int)->Dictionary:
 var block:=floori(float(maxi(slot,0))/16.0)
 if block!=_block or seed_value!=_seed:
  var rng:=RandomNumberGenerator.new()
  rng.seed=seed_value+block*104729
  var calm:Array[int]=[0,1,3,5,7,8,12]
  var strong:Array[int]=[2,4,6,9,10,11,13]
  for group:Array in [calm,strong]:
   for i in range(group.size()-1,0,-1):
    var j:=rng.randi_range(0,i)
    var saved:int=group[i];group[i]=group[j];group[j]=saved
  var order:Array[int]=[14]
  for i in range(7): order.append(strong[i]);order.append(calm[i])
  order.append(15)
  _plans.clear()
  for action:int in order:
   _plans.append({"action":action,"scene":SCENES[action],"direction":-1 if rng.randf()<0.5 else 1,"peak":4.0 if action in [4,6,7] else rng.randf_range(3.4,4.0),"palette":rng.randi_range(0,3),"speed":rng.randf_range(0.85,1.15)})
  _seed=seed_value;_block=block
 return _plans[posmod(slot,16)].duplicate()

func sample(seconds:float,seed_value:int)->Array[Dictionary]:
 var slot:=floori(maxf(seconds,0.0)/PHRASE_SECONDS)
 var plan:=phrase(slot,seed_value)
 return action_sample(plan.action,fposmod(maxf(seconds,0.0),PHRASE_SECONDS),plan.direction,plan.peak,plan.palette,plan.speed)

static func wave(index:float,position:float,count:float)->float:
 return 0.5+0.5*cos((index-position)*TAU/count)

static func action_sample(action:int,t:float,direction:int,peak:float,palette:int,speed:float=1.0)->Array[Dictionary]:
 # Every phrase meets at a live neutral pose, never a blackout of the outer ring.
 var envelope:=smoothstep(3.0,6.0,t)*(1.0-smoothstep(19.0,23.5,t))
 var u:=clampf((t-6.0)/13.0,0.0,1.0)
 var beat:=t*TAU*speed/6.0
 var position:=float(direction)*t*8.0*speed/5.0
 var palette_a:Color=PALETTES[palette][0]
 var palette_b:Color=PALETTES[palette][1]
 var central_action:int=CENTRES[action]
 var main:=0.0
 var flower:=0.0
 match central_action:
  0: main=3.0+1.6*(0.5+0.5*sin(beat*0.5))
  1: main=lerpf(2.0,6.0,smoothstep(0.0,0.85,u))
  2: main=4.0+2.0*pow(0.5+0.5*sin(beat),3.0)
  3: flower=3.0+3.0*sin(PI*u)
  4,5: flower=4.6+1.4*sin(PI*u)
 if action==11:
  var opening:=smoothstep(15.0,18.0,t)
  main*=1.0-opening
  flower=6.0*opening
 # Flower and plume hand over while retaining a visible centre.
 var central_height:=lerpf(3.0,main,envelope)
 var central_color:=FIXED.WARM.lerp(palette_b.lerp(Color.WHITE,0.45),envelope)
 var result:Array[Dictionary]=[{"height":central_height,"color":central_color,"energy":1.6*clampf(central_height/0.5,0.0,1.0),"level":central_height/6.0}]
 var flower_colors:=PackedColorArray()
 var flower_heights:=PackedFloat32Array()
 var flower_reaches:=PackedFloat32Array()
 for i in range(8):
  var rank:=i if direction>0 else 7-i
  var amount:=wave(float(i),position,8.0)
  var height:=lerpf(0.8,peak,amount)
  var inward:=0.0
  match action:
   0: height=1.0+1.4*(0.5+0.5*sin(beat))
   1: height=lerpf(0.9,peak,0.5+0.5*sin(beat+float(i%2)*PI))
   2: height=lerpf(0.9,peak,pow(wave(float(i),position,4.0),3.0))
   3: height=lerpf(0.9,peak,wave(float(i),position,4.0))
   4: height=lerpf(0.5,peak,smoothstep(float(rank),float(rank)+1.0,u*10.0))
   5: height=lerpf(peak,0.6,smoothstep(float(rank),float(rank)+1.0,u*10.0))
   6: height=lerpf(0.5,0.5+float(rank)*(peak-0.5)/7.0,smoothstep(float(rank),float(rank)+1.0,u*11.0))
   7:
    var stair:=fposmod(float(rank)/8.0+t*speed/8.0,1.0)
    height=lerpf(0.5,peak,smoothstep(0.0,0.82,stair)*(1.0-smoothstep(0.82,1.0,stair)))
   8: height=lerpf(0.7,peak,amount);inward=1.0
   9: height=lerpf(0.9,peak,wave(float(i),position,4.0));inward=1.0
   10:
    # Accelerating phase with a broad, growing pressure crest rather than on/off flashes.
    var rotation:=float(direction)*8.0*speed*(t/5.0+t*t/180.0)
    height=lerpf(0.6,peak,wave(float(i),rotation,8.0)*(0.55+0.45*u));inward=1.0
   11: height=2.0+1.4*(0.5+0.5*sin(beat*0.5));inward=1.0
   12: inward=float(i%2);height=lerpf(1.0,peak,wave(float(i),position,4.0))
   13: inward=1.0 if i%4==0 else 0.0
   14: inward=1.0 if i<4 else 0.0
   15:
    # Two broad inward crests move through a continuously upright supporting ring.
    inward=smoothstep(0.55,0.85,wave(float(i),position*0.3,4.0))
  # Alternate groups turn at different times. Other nozzles retain their pressure.
  var offset:=float(i%2)*1.25
  var turn:=smoothstep(0.25+offset,1.25+offset,t)*(1.0-smoothstep(21.0+offset,22.0+offset,t))
  if action==11: inward*=1.0-smoothstep(12.0+offset,13.0+offset,t)
  inward*=turn
  height=lerpf(1.0,height,envelope)*(1.0-0.8*sin(PI*inward))
  var color:=FIXED.ICE.lerp(palette_a.lerp(palette_b,clampf(height/4.0,0.0,1.0)),envelope)
  result.append({"height":height,"inward":inward,"color":color,"energy":(1.25+0.5*height/4.0)*clampf(height/0.5,0.0,1.0),"level":height/4.0})
  var petal:=flower
  if central_action==4: petal*=0.72+0.28*(0.5+0.5*sin(beat+float(i%2)*PI))
  if central_action==5: petal*=0.65+0.35*wave(float(i),position*0.4,8.0)
  petal*=envelope
  flower_heights.append(petal)
  flower_reaches.append(lerpf(2.1,3.2,smoothstep(3.0,6.0,petal)))
  flower_colors.append(FIXED.ICE.lerp(palette_a.lerp(palette_b,petal/6.0),envelope))
 var flower_height:=flower_heights[0]
 for height:float in flower_heights: flower_height=maxf(flower_height,height)
 var flower_energy:=1.6*clampf(flower_height/0.5,0.0,1.0)
 result[0]["flower_height"]=flower_height
 result[0]["flower_heights"]=flower_heights
 result[0]["flower_reaches"]=flower_reaches
 result[0]["flower_reach"]=lerpf(2.1,3.2,smoothstep(3.0,6.0,flower_height))
 result[0]["flower_colors"]=flower_colors
 result[0]["flower_energy"]=flower_energy
 result[0]["climax"]=envelope*smoothstep(3.0,6.0,maxf(main,flower))
 result[0]["light_color"]=central_color.lerp(palette_a,flower_energy/maxf(0.001,flower_energy+float(result[0].energy)))
 result[0]["action"]=ACTIONS[action]
 return result
