# Local CAD fallback policy

Use this route only when the provider CAD skill and native OpenCASCADE/build123d runtime cannot be installed in the current environment.

## Allowed scope

- CAD-L0 through CAD-L3 internal digital prototypes.
- Source-controlled parametric geometry.
- Closed mesh solids, faceted BREP STEP, STL/GLB derivatives, deterministic inspection and snapshots.
- Early supplier discussion and DFM preparation clearly marked not for tooling.

## Forbidden claims

A faceted fallback does not establish native feature history, analytic surfaces, GD&T, tolerance stack, strength, fatigue, assist torque, user safety, tooling readiness or physical production approval. It must never be labeled CAD-L4/L5 or production-frozen.

## Execution order

1. Build CAD Brief and CAD Contract from facts, not from marketing images.
2. Generate project-local `cad/model.py` with named parameters.
3. Run `scripts/local_cad_adapter.py`.
4. Validate every body is closed/winding-consistent and the STEP references are complete.
5. Check key poses, interfaces and forbidden envelopes.
6. Record failed iteration, smallest responsible changes and rerun.
7. Generate BOM, drawing register, controlled release scope and hashes.
8. Run semantic `scripts/e2e_acceptance.py`.

Provider CAD or local native B-Rep remains the preferred route. Rebuild or verify the model there before tooling.
