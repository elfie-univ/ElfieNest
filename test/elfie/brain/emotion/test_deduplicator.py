import importlib.util

spec = importlib.util.spec_from_file_location(
    "deduplicator",
    "/Users/zhenli/git-code/ElfieNest/elfie/brain/emotion/fusion/deduplicator.py",
)
deduplicator_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deduplicator_module)

EventDeduplicator = deduplicator_module.EventDeduplicator
fuse_intensities = deduplicator_module.fuse_intensities

log_lines = []


def log(msg):
    log_lines.append(msg)
    print(msg)


log("=" * 60)
log("TASK-8: EventDeduplicator Test Evidence")
log("=" * 60)

log("\n[TEST 1] Basic Deduplication")
dedup = EventDeduplicator(ttl=60.0)

event_id = "event_001"
result1 = dedup.is_new(event_id, current_time=1000.0)
log(f"  First check for {event_id}: is_new={result1} (expected: True)")
assert result1 == True, "First occurrence should be new"

dedup.mark_processed(event_id, current_time=1000.0)

result2 = dedup.is_new(event_id, current_time=1000.0)
log(f"  Second check for {event_id}: is_new={result2} (expected: False)")
assert result2 == False, "Second occurrence should be duplicate"

log("  ✓ PASSED")

log("\n[TEST 2] TTL Expiration")
dedup2 = EventDeduplicator(ttl=60.0)

event_a = "event_a"
dedup2.mark_processed(event_a, current_time=1000.0)

result_within_ttl = dedup2.is_new(event_a, current_time=1050.0)
log(f"  At T=1050 (50s later): is_new={result_within_ttl} (expected: False)")
assert result_within_ttl == False, "Should still be within TTL"

result_expired = dedup2.is_new(event_a, current_time=1061.0)
log(f"  At T=1061 (61s later): is_new={result_expired} (expected: True)")
assert result_expired == True, "Should have expired"

log("  ✓ PASSED")

log("\n[TEST 3] Weighted Average Fusion")

result_equal = fuse_intensities([1.0, 2.0, 3.0])
log(f"  Equal weights [1,2,3]: {result_equal} (expected: 2.0)")
assert result_equal == 2.0, "Equal weights should give arithmetic mean"

result_weighted = fuse_intensities([1.0, 2.0, 3.0], weights=[1.0, 2.0, 1.0])
log(f"  Weights [1,2,1] on [1,2,3]: {result_weighted} (expected: 2.0)")
assert result_weighted == 2.0, "Weighted average should be 2.0"

result_custom = fuse_intensities([5.0, 10.0], weights=[3.0, 1.0])
log(f"  Weights [3,1] on [5,10]: {result_custom} (expected: 6.25)")
assert abs(result_custom - 6.25) < 0.001, "Weighted average should be 6.25"

log("  ✓ PASSED")

log("\n[TEST 4] Error Handling")

try:
    fuse_intensities([])
    log("  ERROR: Should have raised ValueError for empty list")
    assert False
except ValueError as e:
    log(f"  Empty list raises ValueError: {e} (expected)")

try:
    fuse_intensities([1.0, 2.0], [1.0])
    log("  ERROR: Should have raised ValueError for mismatched lengths")
    assert False
except ValueError as e:
    log(f"  Mismatched lengths raises ValueError: {e} (expected)")

log("  ✓ PASSED")

log("\n" + "=" * 60)
log("ALL TESTS PASSED!")
log("=" * 60)

import os

os.makedirs(".sisyphus/evidence", exist_ok=True)
with open(".sisyphus/evidence/task-8-dedup.log", "w") as f:
    f.write("\n".join(log_lines))
    f.write("\n")

log("\nEvidence saved to: .sisyphus/evidence/task-8-dedup.log")
