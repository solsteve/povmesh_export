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

