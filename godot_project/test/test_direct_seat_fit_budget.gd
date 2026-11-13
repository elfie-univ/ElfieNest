extends SceneTree
## Shared fit scheduling budget: one quarter of a frame, bounded to 8–32 ms.
const SEAT := preload("res://runtime/actor/direct_seat_cycle.gd")

func _initialize() -> void:
	var failures := 0
	for sample: Array in [
		[0.0,8000],
		[1.0/60.0,8000],
		[0.032,8000],
		[0.04,10000],
		[0.1,25000],
		[0.128,32000],
		[0.5,32000],
	]:
		var actual := SEAT.fit_budget_usec(float(sample[0]))
		if actual != int(sample[1]):
			failures += 1
			push_error("Fit budget delta=%s expected=%s actual=%s" % [sample[0],sample[1],actual])
	if failures == 0: print("PASS shared fit budget: 8 ms minimum, 25 percent frame time, 32 ms maximum")
	quit(1 if failures else 0)
