from __future__ import annotations

from pathlib import Path

from .export_types import ImageTextureData, MaterialData


class MaterialExtractor:
    """
    Minimal Phase 2 material extractor.

    Supported pattern
    -----------------
    - one material per object
    - active material preferred
    - material must use nodes
    - active Material Output surface input must be linked
    - linked shader must be a Principled BSDF
    - Base Color may be:
        * an unlinked literal color
        * or an Image Texture node directly linked to Base Color

    Unsupported cases fall back to an unsupported MaterialData record so
    geometry export can continue deterministically.
    """

    @staticmethod
    def extract_material_data(obj, export_name: str) -> MaterialData | None:
        material = MaterialExtractor._choose_material(obj)
        if material is None:
            return None

        if not material.use_nodes or material.node_tree is None:
            return MaterialData(
                source_name=material.name,
                export_name=f"{export_name}_MAT",
                is_supported=False,
                uses_nodes=bool(material.use_nodes),
                base_color=None,
                image_texture=None,
                uses_uv_mapping=False,
                warning="Material does not use nodes.",
            )

        output_node = MaterialExtractor._find_active_output_node(material)
        if output_node is None:
            return MaterialData(
                source_name=material.name,
                export_name=f"{export_name}_MAT",
                is_supported=False,
                uses_nodes=True,
                base_color=None,
                image_texture=None,
                uses_uv_mapping=False,
                warning="No active Material Output node found.",
            )

        surface_input = output_node.inputs.get("Surface")
        if surface_input is None or not surface_input.is_linked:
            return MaterialData(
                source_name=material.name,
                export_name=f"{export_name}_MAT",
                is_supported=False,
                uses_nodes=True,
                base_color=None,
                image_texture=None,
                uses_uv_mapping=False,
                warning="Material Output Surface is not linked.",
            )

        shader_node = surface_input.links[0].from_node
        if shader_node is None or shader_node.type != "BSDF_PRINCIPLED":
            return MaterialData(
                source_name=material.name,
                export_name=f"{export_name}_MAT",
                is_supported=False,
                uses_nodes=True,
                base_color=None,
                image_texture=None,
                uses_uv_mapping=False,
                warning="Only a directly connected Principled BSDF is supported.",
            )

        return MaterialExtractor._extract_principled(shader_node, export_name, material.name)

    @staticmethod
    def _choose_material(obj):
        active = getattr(obj, "active_material", None)
        if active is not None:
            return active

        slots = getattr(obj, "material_slots", None)
        if slots:
            for slot in slots:
                mat = getattr(slot, "material", None)
                if mat is not None:
                    return mat

        return None

    @staticmethod
    def _find_active_output_node(material):
        nodes = material.node_tree.nodes
        active_output = None

        for node in nodes:
            if node.type == "OUTPUT_MATERIAL":
                if getattr(node, "is_active_output", False):
                    return node
                if active_output is None:
                    active_output = node

        return active_output

    @staticmethod
    def _extract_principled(shader_node, export_name: str, material_name: str) -> MaterialData:
        base_color_input = shader_node.inputs.get("Base Color")
        if base_color_input is None:
            return MaterialData(
                source_name=material_name,
                export_name=f"{export_name}_MAT",
                is_supported=False,
                uses_nodes=True,
                base_color=None,
                image_texture=None,
                uses_uv_mapping=False,
                warning="Principled BSDF has no Base Color input.",
            )

        image_texture = None
        base_color = None
        uses_uv_mapping = False

        if base_color_input.is_linked:
            from_node = base_color_input.links[0].from_node
            if from_node is None or from_node.type != "TEX_IMAGE":
                return MaterialData(
                    source_name=material_name,
                    export_name=f"{export_name}_MAT",
                    is_supported=False,
                    uses_nodes=True,
                    base_color=None,
                    image_texture=None,
                    uses_uv_mapping=False,
                    warning="Only a direct Image Texture -> Base Color link is supported.",
                )

            image = getattr(from_node, "image", None)
            if image is None:
                return MaterialData(
                    source_name=material_name,
                    export_name=f"{export_name}_MAT",
                    is_supported=False,
                    uses_nodes=True,
                    base_color=None,
                    image_texture=None,
                    uses_uv_mapping=False,
                    warning="Image Texture node has no image assigned.",
                )

            raw_path = str(getattr(image, "filepath", "") or "")
            resolved_path = raw_path

            try:
                import bpy  # local import keeps this module import-safe outside Blender
                resolved_path = bpy.path.abspath(raw_path) if raw_path else raw_path
            except Exception:
                resolved_path = raw_path

            image_texture = ImageTextureData(
                source_name=material_name,
                image_name=str(getattr(image, "name", "") or ""),
                filepath_raw=raw_path,
                filepath_resolved=resolved_path,
                exists_on_disk=bool(resolved_path and Path(resolved_path).exists()),
                uses_uv_mapping=True,
            )
            uses_uv_mapping = True
        else:
            default = base_color_input.default_value
            base_color = (
                float(default[0]),
                float(default[1]),
                float(default[2]),
            )

        return MaterialData(
            source_name=material_name,
            export_name=f"{export_name}_MAT",
            is_supported=True,
            uses_nodes=True,
            base_color=base_color,
            image_texture=image_texture,
            uses_uv_mapping=uses_uv_mapping,
            warning="",
        )
