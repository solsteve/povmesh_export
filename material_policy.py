from __future__ import annotations

from dataclasses import replace

from .export_types import (
    AlphaSourceKind,
    ExportOptions,
    FinishData,
    MaterialData,
    TransparencyData,
    TransparencyMode,
)


class MaterialPolicy:
    @staticmethod
    def normalize(material: MaterialData, export_options: ExportOptions | None = None) -> MaterialData:
        if export_options is None:
            export_options = ExportOptions()

        transparency = material.transparency

        # Be tolerant of partially populated Phase 3 / early Phase 4 materials.
        alpha_scalar = transparency.alpha_scalar
        if alpha_scalar is None:
            alpha_scalar = 1.0

        alpha_scalar = MaterialPolicy._clamp_unit(alpha_scalar, default=1.0)
        image_has_alpha = bool(transparency.image_has_alpha)
        alpha_source_kind = MaterialPolicy._infer_alpha_source_kind(alpha_scalar, image_has_alpha)

        mode = transparency.mode
        if mode == TransparencyMode.AUTO:
            mode = export_options.transparency_mode
        if mode == TransparencyMode.AUTO:
            mode = TransparencyMode.TRANSMIT

        normalized_transparency = TransparencyData(
            alpha_scalar=alpha_scalar,
            image_has_alpha=image_has_alpha,
            alpha_source_kind=alpha_source_kind,
            mode=mode,
            is_transparent=(alpha_source_kind != AlphaSourceKind.NONE),
            scalar_transmit=max(0.0, min(1.0, 1.0 - alpha_scalar)),
        )

        finish = FinishData(
            roughness=MaterialPolicy._clamp_unit(material.roughness, default=1.0),
            specular=MaterialPolicy._clamp_unit(material.specular, default=0.0),
            metallic=MaterialPolicy._clamp_unit(material.metallic, default=0.0),
        )

        return replace(material, transparency=normalized_transparency, finish=finish)

    @staticmethod
    def should_emit_hollow(material: MaterialData) -> bool:
        material = MaterialPolicy.normalize(material)

        # Current Phase 4 rule:
        # - SCALAR only -> real scalar transmission -> hollow/interior allowed
        # - IMAGE only -> cutout/masked transparency -> no hollow/interior
        # - SCALAR_TIMES_IMAGE -> currently downgraded to image-alpha-only in
        #   writers_material.py, so wrapper must also avoid hollow/interior
        kind = material.transparency.alpha_source_kind
        return kind == AlphaSourceKind.SCALAR

    @staticmethod
    def should_emit_interior(material: MaterialData) -> bool:
        material = MaterialPolicy.normalize(material)
        return material.ior is not None and MaterialPolicy.should_emit_hollow(material)

    @staticmethod
    def map_finish(material: MaterialData) -> dict[str, float]:
        material = MaterialPolicy.normalize(material)

        roughness = MaterialPolicy._clamp_unit(material.roughness, default=1.0)
        specular = MaterialPolicy._clamp_unit(material.specular, default=0.0)
        metallic = MaterialPolicy._clamp_unit(material.metallic, default=0.0)

        phong = specular * (1.0 - roughness)
        reflection = metallic * 0.5

        emission_strength = 0.0
        if material.emission.is_emissive:
            emission_strength = max(0.0, float(material.emission.strength))

        return {
            "roughness": roughness,
            "specular": specular,
            "metallic": metallic,
            "phong": phong,
            "reflection": reflection,
            "diffuse": 0.8,
            "phong_size": 40.0,
            "emission_strength": emission_strength,
        }

    @staticmethod
    def _infer_alpha_source_kind(alpha_scalar: float, image_has_alpha: bool) -> AlphaSourceKind:
        has_scalar_alpha = alpha_scalar < 0.999

        if has_scalar_alpha and image_has_alpha:
            return AlphaSourceKind.SCALAR_TIMES_IMAGE
        if has_scalar_alpha:
            return AlphaSourceKind.SCALAR
        if image_has_alpha:
            return AlphaSourceKind.IMAGE
        return AlphaSourceKind.NONE

    @staticmethod
    def _clamp_unit(value: float | None, default: float) -> float:
        if value is None:
            return default
        try:
            value = float(value)
        except (TypeError, ValueError):
            return default
        return max(0.0, min(1.0, value))

