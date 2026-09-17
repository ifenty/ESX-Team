"""One explicit diffusion step on a uniform periodic one-dimensional grid.

The stencil approximates dT/dt = kappa d2T/dx2 with r=kappa*dt/dx**2.
The conservative simultaneous update requires 0 <= r <= 1/2 for this scheme.
"""
import math


def step(tracer, r):
    """Return a new periodic tracer state; reject a nonfinite or unstable r."""
    if len(tracer) < 3 or not math.isfinite(r) or not 0 <= r <= 0.5:
        raise ValueError('at least three cells and finite 0 <= r <= 0.5 required')
    if not all(math.isfinite(x) for x in tracer):
        raise ValueError('tracer must be finite')
    return [x + r * (tracer[(i-1) % len(tracer)] - 2*x + tracer[(i+1) % len(tracer)])
            for i, x in enumerate(tracer)]
