from __future__ import annotations

from typing import Iterable, TextIO

from .export_types import AlphaSourceKind, MaterialData, TransparencyMode
from .material_policy import MaterialPolicy


class MaterialWriter:
    @staticmethod
    def write_material_declarations(
        f: TextIO,
        material_records: Iterable[MaterialData],
        include_comments: bool = True,
    ) -> None:
        material_list = [mat for mat in material_records if mat is not None]
        if not material_list:
            return

        if include_comments:
            f.write("// ------------------------------------------------------------\n")
            f.write("// Material declarations\n")
            f.write("// ------------------------------------------------------------\n")

        for material in material_list:
            MaterialWriter.write_material_declaration(
                f,
                material,
                include_comments=include_comments,
            )
            f.write("\n")

    @staticmethod
    def write_material_declaration(
        f: TextIO,
        material: MaterialData,
        include_comments: bool = True,
    ) -> None:
        material = MaterialPolicy.normalize(material)

        if not material.is_supported:
            MaterialWriter._write_fallback_material(
                f,
                material,
                include_comments=include_comments,
            )
            return

        if material.image_texture is not None:
            MaterialWriter._write_image_texture_material(
                f,
                material,
                include_comments=include_comments,
            )
            return

        if material.base_color is not None:
            MaterialWriter._write_solid_color_material(f, material)
            return

        MaterialWriter._write_fallback_material(
            f,
            material,
            include_comments=include_comments,
        )

    @staticmethod
    def _linear_to_srgb_channel(c: float) -> float:
        c = max(0.0, min(1.0, float(c)))
        if c <= 0.0031308:
            return 12.92 * c
        return 1.055 * (c ** (1.0 / 2.4)) - 0.055

    @staticmethod
    def _write_solid_color_material(f: TextIO, material: MaterialData) -> None:
        assert material.base_color is not None

        r_lin, g_lin, b_lin = material.base_color
        r = MaterialWriter._linear_to_srgb_channel(r_lin)
        g = MaterialWriter._linear_to_srgb_channel(g_lin)
        b = MaterialWriter._linear_to_srgb_channel(b_lin)

        f.write(f"#declare {material.export_name}_MAT = texture {{\n")
        f.write("    pigment {\n")
        f.write(
            f"        color srgb <{MaterialFormatters.float(r)}, {MaterialFormatters.float(g)}, {MaterialFormatters.float(b)}>"
        )
        MaterialWriter._write_transparency_terms_for_solid(f, material)
        f.write("\n")
        f.write("    }\n")
        MaterialWriter._write_finish_block(f, material)
        f.write("}\n")

    @staticmethod
    def _write_image_texture_material(
        f: TextIO,
        material: MaterialData,
        include_comments: bool = True,
    ) -> None:
        image = material.image_texture
        assert image is not None

        image_path = image.emitted_path or image.filepath_resolved or image.filepath_raw or image.image_name
        image_path = MaterialFormatters.escape_pov_string(image_path)

        f.write(f"#declare {material.export_name}_MAT = texture {{\n")
        f.write("    uv_mapping\n")
        f.write("    pigment {\n")
        f.write("        image_map {\n")
        f.write(f'            {MaterialWriter._image_map_type_token(image_path)} "{image_path}"\n')
        MaterialWriter._write_transparency_terms_for_image(
            f,
            material,
            include_comments=include_comments,
        )
        f.write("            once\n")
        f.write("        }\n")
        f.write("        scale <1, -1, 1>\n")
        f.write("        rotate <0, 0, 180>\n")
        f.write("        translate <1, 0, 1>\n")
        f.write("    }\n")
        MaterialWriter._write_finish_block(f, material)
        f.write("}\n")

    @staticmethod
    def _write_fallback_material(
        f: TextIO,
        material: MaterialData,
        include_comments: bool = True,
    ) -> None:
        if include_comments and material.warning:
            f.write(f"// Material fallback for {material.source_name}: {material.warning}\n")

        f.write(f"#declare {material.export_name}_MAT = texture {{\n")
        f.write("    pigment {\n")
        f.write("        color srgb <0.8, 0.8, 0.8>\n")
        f.write("    }\n")
        MaterialWriter._write_finish_block(f, material)
        f.write("}\n")

    @staticmethod
    def _write_transparency_terms_for_solid(f: TextIO, material: MaterialData) -> None:
        transmit = material.transparency.scalar_transmit
        if transmit <= 1.0e-9:
            return

        if material.transparency.mode == TransparencyMode.FILTER:
            f.write(f" filter {MaterialFormatters.float(transmit)}")
        else:
            f.write(f" transmit {MaterialFormatters.float(transmit)}")

    @staticmethod
    def _write_transparency_terms_for_image(
        f: TextIO,
        material: MaterialData,
        include_comments: bool = True,
    ) -> None:
        transmit = material.transparency.scalar_transmit
        kind = material.transparency.alpha_source_kind

        if transmit <= 1.0e-9:
            return

        # Phase 4 policy:
        # - IMAGE only: let the PNG/TGA alpha channel speak for itself
        # - SCALAR only: not expected here, but if encountered, allow transmit-all
        # - SCALAR_TIMES_IMAGE: do NOT emit transmit-all for normal PNG image_map
        #   because this case has proven unreliable in POV-Ray 3.7 workflows.
        if kind == AlphaSourceKind.IMAGE:
            return

        if kind == AlphaSourceKind.SCALAR_TIMES_IMAGE:
            if include_comments:
                f.write("            // WARNING: image alpha + scalar alpha requested\n")
                f.write("            // Exporter emitted image alpha only\n")
                f.write("            // Reason: PNG image_map 'transmit all' is unreliable for this case in POV-Ray 3.7\n")
            return

        keyword = "filter all" if material.transparency.mode == TransparencyMode.FILTER else "transmit all"
        f.write(f"            {keyword} {MaterialFormatters.float(transmit)}\n")

    @staticmethod
    def _write_finish_block(handle: TextIO, material: MaterialData) -> None:
        values = MaterialPolicy.map_finish(material)

        handle.write("    // pov == blender\n")
        handle.write(f"    // phong == roughness: {values['roughness']:.3f}\n")
        handle.write(f"    // specular == specular: {values['specular']:.3f}\n")
        handle.write(f"    // reflection == metallic: {values['metallic']:.3f}\n")

        if material.alpha is not None:
            handle.write(f"    // alpha == alpha: {material.alpha:.3f}\n")
        if material.ior is not None:
            handle.write(f"    // ior == ior: {material.ior:.3f}\n")
        if material.emission.color is not None:
            r, g, b = material.emission.color
            handle.write(f"    // emission == emission color: <{r:.3f}, {g:.3f}, {b:.3f}>\n")
            handle.write(f"    // emission_strength == emission strength: {material.emission.strength:.3f}\n")

        handle.write("    finish {\n")
        handle.write(f"        diffuse {values['diffuse']:.6f}\n")
        handle.write(f"        phong {values['phong']:.6f}\n")
        handle.write(f"        specular {values['specular']:.6f}\n")
        handle.write(f"        phong_size {values['phong_size']:.6f}\n")
        handle.write(f"        reflection {values['reflection']:.6f}\n")
        handle.write(f"        roughness {values['roughness']:.6f}\n")

        if material.emission.is_emissive and material.emission.color is not None:
            er, eg, eb = material.emission.color
            strength = values["emission_strength"]
            handle.write(
                f"        emission <{MaterialFormatters.float(er * strength)}, "
                f"{MaterialFormatters.float(eg * strength)}, "
                f"{MaterialFormatters.float(eb * strength)}>\n"
            )

        handle.write("    }\n")

    @staticmethod
    def _image_map_type_token(path_str: str) -> str:
        lower = path_str.lower()
        if lower.endswith(".png"):
            return "png"
        if lower.endswith(".jpg") or lower.endswith(".jpeg"):
            return "jpeg"
        if lower.endswith(".tga"):
            return "tga"
        if lower.endswith(".bmp"):
            return "bmp"
        if lower.endswith(".gif"):
            return "gif"
        if lower.endswith(".iff"):
            return "iff"
        if lower.endswith(".ppm") or lower.endswith(".pgm"):
            return "ppm"
        if lower.endswith(".tiff") or lower.endswith(".tif"):
            return "tiff"
        if lower.endswith(".exr"):
            return "exr"
        return "png"


class MaterialFormatters:
    @staticmethod
    def float(value: float) -> str:
        return f"{float(value):.9g}"

    @staticmethod
    def escape_pov_string(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')
