# Periodic diffusion demonstration profile

This synthetic CPU example qualifies a single uniform periodic explicit diffusion
stencil. Tracer values are dimensionless. The ratio r=kappa*dt/dx^2 is finite and
between zero and one half. All cells are wet, the grid is one dimensional and
there is no external dataset, MPI, adjoint, statistical training or field-data claim.

The oracle is the discrete Fourier eigenvalue 1-4*r*sin(pi/N)^2 raised to the
number of time steps. Tests cover conservation, finite samples, nontrivial decay
and rejection of invalid ratios. Error tolerances are absolute for float64 at
N=32 and twelve steps. Full PDE convergence and realistic coastlines are outside
this demonstration. Python standard library and a local CPU are sufficient.

Communication is disabled. Commits, publication and paid compute require owner
authorization. Artifacts stay under the project's ignored loop state. No domain
specialist skill is needed. The project uses the ESX default role definitions;
the deploying owner verifies the actual agent runtime and resume support.
