"""Independent discrete Fourier-mode oracle plus mass and refusal checks."""
import math
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from diffusion import step

if not __debug__:
    raise SystemExit('Scientific assertions must be enabled; remove -O/PYTHONOPTIMIZE.')

n, r, steps = 32, 0.2, 12
initial = [1 + 0.3*math.cos(2*math.pi*i/n) for i in range(n)]
tracer = initial[:]
for _ in range(steps):
    tracer = step(tracer, r)
factor = (1 - 4*r*math.sin(math.pi/n)**2)**steps
expected = [1 + 0.3*factor*math.cos(2*math.pi*i/n) for i in range(n)]
error = max(abs(a-b) for a,b in zip(tracer, expected))
assert len(tracer) == n and all(math.isfinite(x) for x in tracer)
assert error < 2e-14, error
assert abs(sum(tracer)-sum(initial)) < 2e-13
assert max(tracer) < max(initial) and min(tracer) > min(initial)
for invalid in (-0.1, 0.51, float('nan')):
    try:
        step(initial, invalid)
    except ValueError:
        pass
    else:
        raise AssertionError('invalid diffusion ratio accepted')
print(f'PASS: {n} cells, {steps} steps, Fourier error={error:.17g}')
