# povmesh_export

Suggested implementation sequence
I would implement Phase 3 in this order:

- Add slot-based material extraction
    - new extractor entry point for a specific material slot

- Refactor mesh extraction
    - split loop triangles by material index
    - return a list of per-material ObjectMeshData parts

- Update pipeline record creation
    - one source object can append several export records

- Update naming policy
    - add material-aware part suffixes

- Update comments/header text
    - reflect per-object multi-part export

- Test cases
    - one object, two materials, both solid colors
    - one object, two materials, one solid + one image texture
    - multiple objects, each with multiple materials
    - empty slot / unsupported shader / no material
    - UV-mapped texture on one sub-part only











What we’ll do next (focused and controlled)
We’ll implement edge-case handling + output polish in a safe, incremental way.

Scope of this step
We are not changing core behavior, only stabilizing it.

We will:

1. Stable, deterministic part naming
Guarantee:

no collisions

readable names

consistent across runs

Handle:

empty material names

duplicate material names

same material used in multiple slots

2. Explicit fallback behavior
Define and enforce:

invalid slot index → fallback bucket

empty slot → fallback bucket

unsupported material → already handled, just ensure naming is stable

3. Consistent final asset rule
Ensure:

if any object splits → final asset is always a union
(no accidental single-object output)

4. Minor output polish
cleaner comments in SDL

optional slot index annotation (helps debugging)

