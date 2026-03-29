from __future__ import annotations

from typing import Optional
import os

import bpy

from .export_types import (
    AlphaSourceKind,
    ColorRGB,
    EmissionData,
    FinishData,
    ImageTextureData,
    MaterialData,
    TransparencyData,
)


class MaterialExtractor:
    @staticmethod
    def extract_material_data(obj, export_name: str) -> Optional[MaterialData]:
        mat = obj.active_material
        if mat is None and len(obj.material_slots) > 0:
            mat = obj.material_slots[0].material

        if mat is None:
            return MaterialExtractor._build_fallback(export_name, "NO_MATERIAL")

        return MaterialExtractor._extract_from_material(mat, export_name)

    @staticmethod
    def extract_material_data_for_slot(obj, material_slot_index: int, export_name: str) -> MaterialData:
        if len(obj.material_slots) == 0:
            return MaterialExtractor._build_fallback(export_name, "NO_SLOTS")
        if material_slot_index < 0 or material_slot_index >= len(obj.material_slots):
            return MaterialExtractor._build_fallback(export_name, "INVALID_SLOT")

        slot = obj.material_slots[material_slot_index]
        mat = slot.material
        if mat is None:
            return MaterialExtractor._build_fallback(export_name, "UNASSIGNED")

        return MaterialExtractor._extract_from_material(mat, export_name)

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

    @staticmethod
    def _extract_from_material(mat, export_name: str) -> MaterialData:
        if not mat.use_nodes:
            return MaterialExtractor._build_fallback(export_name, "NO_NODES")

        nodes = mat.node_tree.nodes
        principled = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if principled is None:
            return MaterialExtractor._build_fallback(export_name, "NO_PRINCIPLED")

        base_color_input = principled.inputs.get("Base Color")
        if base_color_input is None:
            return MaterialExtractor._build_fallback(export_name, "NO_BASE_COLOR")

        alpha = MaterialExtractor._get_socket_value(principled, "Alpha")
        roughness = MaterialExtractor._get_socket_value(principled, "Roughness")
        specular = MaterialExtractor._get_specular(principled)
        metallic = MaterialExtractor._get_socket_value(principled, "Metallic")
        ior = MaterialExtractor._get_socket_value(principled, "IOR")
        emission = MaterialExtractor._get_emission_data(principled)

        if base_color_input.is_linked:
            from_node = base_color_input.links[0].from_node
            if from_node.type != 'TEX_IMAGE':
                return MaterialExtractor._build_fallback(export_name, "UNSUPPORTED_LINK")

            image = from_node.image
            if image is None:
                return MaterialExtractor._build_fallback(export_name, "NO_IMAGE")

            image_path = bpy.path.abspath(image.filepath)
            image_has_alpha = MaterialExtractor._get_image_has_alpha(image)
            texture = ImageTextureData(
                source_name=mat.name,
                image_name=str(getattr(image, "name", "") or ""),
                filepath_raw=str(getattr(image, "filepath", "") or ""),
                filepath_resolved=image_path,
                exists_on_disk=os.path.exists(image_path) if image_path else False,
                uses_uv_mapping=True,
                has_alpha_channel=image_has_alpha,
                emitted_path=image_path,
            )
            transparency = MaterialExtractor._build_transparency_data(alpha, image_has_alpha)
            return MaterialData(
                source_name=mat.name,
                export_name=export_name,
                is_supported=True,
                uses_nodes=True,
                image_texture=texture,
                uses_uv_mapping=True,
                finish=FinishData(roughness=roughness, specular=specular, metallic=metallic),
                transparency=transparency,
                emission=emission,
                ior=ior,
            )

        color = base_color_input.default_value
        transparency = MaterialExtractor._build_transparency_data(alpha, image_has_alpha=False)
        return MaterialData(
            source_name=mat.name,
            export_name=export_name,
            is_supported=True,
            uses_nodes=True,
            base_color=(float(color[0]), float(color[1]), float(color[2])),
            uses_uv_mapping=False,
            finish=FinishData(roughness=roughness, specular=specular, metallic=metallic),
            transparency=transparency,
            emission=emission,
            ior=ior,
        )

    @staticmethod
    def _get_socket_value(node, name: str) -> Optional[float]:
        sock = node.inputs.get(name)
        if sock is None:
            return None
        try:
            return float(sock.default_value)
        except Exception:
            return None

    @staticmethod
    def _get_specular(node) -> Optional[float]:
        sock = node.inputs.get("Specular") or node.inputs.get("Specular IOR Level")
        if sock is None:
            return None
        try:
            return float(sock.default_value)
        except Exception:
            return None

    @staticmethod
    def _get_emission_data(principled) -> EmissionData:
        color_sock = principled.inputs.get("Emission Color") or principled.inputs.get("Emission")
        strength_sock = principled.inputs.get("Emission Strength")

        color: Optional[ColorRGB] = None
        if color_sock is not None:
            try:
                value = color_sock.default_value
                color = (float(value[0]), float(value[1]), float(value[2]))
            except Exception:
                color = None

        strength = 0.0
        if strength_sock is not None:
            try:
                strength = float(strength_sock.default_value)
            except Exception:
                strength = 0.0

        is_emissive = (
            color is not None and any(channel > 1.0e-6 for channel in color) and strength > 1.0e-6
        )
        return EmissionData(color=color, strength=strength, is_emissive=is_emissive)

    @staticmethod
    def _get_image_has_alpha(image) -> bool:
        try:
            alpha_mode = str(getattr(image, "alpha_mode", "") or "").upper()
            channels = int(getattr(image, "channels", 0) or 0)
            depth = int(getattr(image, "depth", 0) or 0)
            return alpha_mode not in {"NONE", ""} or channels == 4 or depth in {32, 64, 128}
        except Exception:
            return False

    @staticmethod
    def _build_transparency_data(alpha_scalar: Optional[float], image_has_alpha: bool) -> TransparencyData:
        alpha = 1.0 if alpha_scalar is None else max(0.0, min(1.0, float(alpha_scalar)))
        if alpha < 0.999 and image_has_alpha:
            source_kind = AlphaSourceKind.SCALAR_TIMES_IMAGE
        elif alpha < 0.999:
            source_kind = AlphaSourceKind.SCALAR
        elif image_has_alpha:
            source_kind = AlphaSourceKind.IMAGE
        else:
            source_kind = AlphaSourceKind.NONE

        return TransparencyData(
            alpha_scalar=alpha,
            image_has_alpha=image_has_alpha,
            alpha_source_kind=source_kind,
            is_transparent=(alpha < 0.999) or image_has_alpha,
            scalar_transmit=max(0.0, min(1.0, 1.0 - alpha)),
        )

    @staticmethod
    def _build_fallback(export_name: str, reason: str) -> MaterialData:
        return MaterialData(
            source_name=reason,
            export_name=export_name,
            is_supported=False,
            uses_nodes=False,
            warning=reason,
            finish=FinishData(roughness=1.0, specular=0.0, metallic=0.0),
        )
