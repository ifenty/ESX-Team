# Deployment examples

`periodic_diffusion/` is a runnable Python-standard-library demonstration. It has
an actual numerical update and an independent discrete Fourier oracle. See the
kit README for installation. It makes no real-data or geophysical-model claim.

For an observational analysis project, source_paths might be `["analysis"]`,
test_paths `["validation"]`, and configuration_paths `["environment.yml", "configs"]`.
Specify longitude/latitude reference, calendar/time matching, quality flags,
uncertainty, missing values, dataset provenance and independent preprocessing checks.

For a Fortran/MPI model, use the real source and test directories, compiler/MPI
version probes and a small grid test harness. Define decomposition, wet masks,
halo conventions, conservation and solver tolerances. An approved remote suite
must wait for the job and return its checked numerical result. Use file/module
navigation for Fortran plus the project's language-aware tools.

For inverse/ML research, specify controls/objectives, identifiability, train/test
separation, frozen preprocessing statistics, transparent baselines, seeds/replicates,
uncertainty and meaningful held-out skill. Scientific acceptance belongs in actual
test commands and the project profile; ESX supplies their workflow and provenance.
