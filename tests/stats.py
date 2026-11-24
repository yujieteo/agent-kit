"""tests/stats.py: the 95% Wilson ranges that the README gives for 4 cases.

Run from the repository: python3 tests/stats.py (exit 0 when all match).
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kit.common import mcnemar, wilson  # noqa: E402

fail = 0
for k, n, want in [(3, 4, (0.30, 0.95)), (0, 4, (0.00, 0.49)), (1, 4, (0.05, 0.70))]:
    got = tuple(round(x, 2) for x in wilson(k, n))
    ok = got == want
    fail |= not ok
    print(f"{'ok  ' if ok else 'BAD '} wilson({k},{n}) = [{got[0]:.2f}, {got[1]:.2f}], want [{want[0]:.2f}, {want[1]:.2f}]")
ok = all(math.isnan(x) for x in wilson(0, 0))
fail |= not ok
print(f"{'ok  ' if ok else 'BAD '} wilson(0,0) has no range")
ok = mcnemar(0, 0) == 1.0 and abs(mcnemar(6, 0) - 2 / 64) < 1e-12
fail |= not ok
print(f"{'ok  ' if ok else 'BAD '} mcnemar(0,0) = 1, mcnemar(6,0) = 2/64")
sys.exit(fail)
