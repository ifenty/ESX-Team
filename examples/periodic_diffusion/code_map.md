# Diffusion code map

## Pipeline

The update lives at `src/diffusion.py::step`. It accepts a finite periodic tracer
and stable nondimensional diffusion ratio, returning a simultaneous new state.
Its independent Fourier-mode, conservation and refusal oracle is
`tests/check_diffusion.py::<module>`.

## Verification routes

Run `python3 tests/check_diffusion.py`. The focused and scientific suites use this
small complete demonstration acceptance set. Structural checks use the ESX audit.
