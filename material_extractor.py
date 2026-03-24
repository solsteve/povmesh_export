from typing import Optional
import bpy

from .export_types import (
    MaterialData,
    ColorRGB,
    ImageTextureData
)


class MaterialExtractor:


    @staticmethod
    def extract_material_data(obj, export_name: str) -> Optional[MaterialData]:
        """
        Phase 2 compatibility path (single material).
        Uses active material if present, else first slot.
        """
        mat = obj.active_material
        if mat is None and len(obj.material_slots) > 0:
            mat = obj.material_slots[0].material

        if mat is None:
            return MaterialExtractor._build_fallback(export_name, "NO_MATERIAL")

        return MaterialExtractor._extract_from_material(mat, export_name)

    # -------------------------------------------------------------------------
    # Phase 3 entry point
    # -------------------------------------------------------------------------

    @staticmethod
    def extract_material_data_for_slot(
        obj,
        material_slot_index: int,
        export_name: str
    ) -> MaterialData:

        # No slots at all
        if len(obj.material_slots) == 0:
            return MaterialExtractor._build_fallback(export_name, "NO_SLOTS")

        # Invalid slot index
        if material_slot_index < 0 or material_slot_index >= len(obj.material_slots):
            return MaterialExtractor._build_fallback(export_name, "INVALID_SLOT")

        slot = obj.material_slots[material_slot_index]
        mat = slot.material

        # Empty slot
        if mat is None:
            return MaterialExtractor._build_fallback(export_name, "UNASSIGNED")

        return MaterialExtractor._extract_from_material(mat, export_name)

    # -------------------------------------------------------------------------
    # Utility: slot name
    # -------------------------------------------------------------------------

    @staticmethod
    def get_slot_material_name(obj, material_slot_index: int) -> str:
        if len(obj.material_slots) == 0:
            return "NO_SLOTS"

        if material_slot_index < 0 or material_slot_index >= len(obj.material_slots):
            return "INVALID_SLOT"

        mat = obj.material_slots[material_slot_index].material
        if mat is None:
            return "UNASSIGNED"

        return mat.name

    # -------------------------------------------------------------------------
    # Core extraction
    # -------------------------------------------------------------------------

    @staticmethod
    def _extract_from_material(mat, export_name: str) -> MaterialData:

        if not mat.use_nodes:
            return MaterialExtractor._build_fallback(export_name, "NO_NODES")

        nodes = mat.node_tree.nodes

        principled = None
        for n in nodes:
            if n.type == 'BSDF_PRINCIPLED':
                principled = n
                break

        if principled is None:
            return MaterialExtractor._build_fallback(export_name, "NO_PRINCIPLED")

        # ---------------------------------------------------------------------
        # Base color handling
        # ---------------------------------------------------------------------

        base_color_input = principled.inputs.get("Base Color")

        if base_color_input is None:
            return MaterialExtractor._build_fallback(export_name, "NO_BASE_COLOR")

        # Case 1: Linked image texture
        if base_color_input.is_linked:
            link = base_color_input.links[0]
            from_node = link.from_node

            if from_node.type == 'TEX_IMAGE':
                image = from_node.image

                if image is None:
                    return MaterialExtractor._build_fallback(export_name, "NO_IMAGE")

                image_path = bpy.path.abspath(image.filepath)

                return MaterialData(
                    source_name=mat.name,
                    export_name=export_name,
                    is_supported=True,
                    uses_nodes=True,
                    image_texture=ImageTextureData(
                        image_path=image_path,
                        interpolation="bilinear"
                    ),
                    uses_uv_mapping=True,
                    roughness=MaterialExtractor._get_socket_value(principled, "Roughness"),
                    specular=MaterialExtractor._get_specular(principled),
                    metallic=MaterialExtractor._get_socket_value(principled, "Metallic")
                )

            else:
                return MaterialExtractor._build_fallback(export_name, "UNSUPPORTED_LINK")

        # Case 2: Direct color
        color = base_color_input.default_value  # RGBA

        print('COLOR = ', [c for c in color])

        return MaterialData(
            source_name=mat.name,
            export_name=export_name,
            is_supported=True,
            uses_nodes=True,
            base_color=(
                float(color[0]),
                float(color[1]),
                float(color[2]),
            ),
            uses_uv_mapping=False,
            roughness=MaterialExtractor._get_socket_value(principled, "Roughness"),
            specular=MaterialExtractor._get_specular(principled),
            metallic=MaterialExtractor._get_socket_value(principled, "Metallic"),
        )

    # -------------------------------------------------------------------------
    # Socket helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _get_socket_value(node, name: str) -> Optional[float]:
        sock = node.inputs.get(name)
        if sock is None:
            return None
        return float(sock.default_value)

    @staticmethod
    def _get_specular(node) -> Optional[float]:
        sock = (
            node.inputs.get("Specular") or
            node.inputs.get("Specular IOR Level")
        )
        if sock is None:
            return None
        return float(sock.default_value)

    # -------------------------------------------------------------------------
    # Fallback builder
    # -------------------------------------------------------------------------

    @staticmethod
    def _build_fallback(export_name: str, reason: str) -> MaterialData:
        return MaterialData(
            source_name=reason,
            export_name=export_name,
            is_supported=False,
            uses_nodes=False,
            warning=reason,
            roughness=1.0,
            specular=0.0,
            metallic=0.0
        )
