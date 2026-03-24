from __future__ import annotations

from typing import Iterable, TextIO

from .export_types import MaterialData


class MaterialWriter:
    """
    Writes minimal material declarations.

    Supported outputs
    -----------------
    - solid Base Color from Principled BSDF
    - Image Texture directly feeding Base Color

    Image texture output uses the confirmed POV-Ray correction:
        once
        scale <1,-1,1>
        rotate <0,0,180>
        translate <1,0,1>
    """

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
        if not material.is_supported:
            MaterialWriter._write_fallback_material(
                f,
                material,
                include_comments=include_comments,
            )
            return

        if material.image_texture is not None:
            MaterialWriter._write_image_texture_material(f, material)
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
    def _write_solid_color_material(f: TextIO, material: MaterialData) -> None:
        r, g, b = material.base_color
        f.write(f"#declare {material.export_name} = texture {{\n")
        f.write("    pigment {\n")
        f.write(
            f"        color rgb <{MaterialFormatters.float(r)}, {MaterialFormatters.float(g)}, {MaterialFormatters.float(b)}>\n"
        )
        f.write("    }\n")
        MaterialWriter._write_finish_block(f, material)
        f.write("}\n")

    @staticmethod
    def _write_image_texture_material(f: TextIO, material: MaterialData) -> None:
        image = material.image_texture
        image_path = image.filepath_resolved or image.filepath_raw or image.image_name
        image_path = MaterialFormatters.escape_pov_string(image_path)

        f.write(f"#declare {material.export_name} = texture {{\n")
        f.write("    uv_mapping\n")
        f.write("    pigment {\n")
        f.write("        image_map {\n")
        f.write(f'            {MaterialWriter._image_map_type_token(image_path)} "{image_path}"\n')
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
        f.write(f"#declare {material.export_name} = texture {{\n")
        f.write("    pigment {\n")
        f.write("        color srgb <0.8, 0.8, 0.8>\n")
        f.write("    }\n")
        f.write("    finish {\n")
        f.write("        ambient 1\n")
        f.write("        diffuse 0.8\n")
        f.write("        specular 0\n")
        f.write("        roughness 1\n")
        f.write("    }\n")
        f.write("}\n")

    @staticmethod
    def _write_finish_block(handle, material_data):
        """
        Write POV-Ray finish block plus debug/mapping comments.

        Mapping comments show which Blender inputs fed which POV parameters.
        Raw debug comments show the extracted Blender-side values directly.
        """

        roughness = material_data.roughness if material_data.roughness is not None else 1.0
        specular = material_data.specular if material_data.specular is not None else 0.0
        metallic = material_data.metallic if material_data.metallic is not None else 0.0

        phong = specular * (1.0 - roughness)
        reflection = metallic * 0.5

        handle.write("    // pov == blender\n")
        handle.write(f"    // phong == roughness: {roughness:.3f}\n")
        handle.write(f"    // specular == specular: {specular:.3f}\n")
        handle.write(f"    // reflection == metallic: {metallic:.3f}\n")
        handle.write("\n")
        handle.write("    // debug material inputs\n")
        handle.write(f"    // roughness raw: {roughness:.3f}\n")
        handle.write(f"    // specular raw: {specular:.3f}\n")
        handle.write(f"    // metallic raw: {metallic:.3f}\n")

        handle.write("    finish {\n")
        handle.write("        ambient 1\n")
        handle.write("        diffuse 0.8\n")
        handle.write(f"        phong {phong:.6f}\n")
        handle.write(f"        specular {specular:.6f}\n")
        handle.write("        phong_size 40\n")
        handle.write(f"        reflection {reflection:.6f}\n")
        handle.write(f"        roughness {roughness:.6f}\n")
        handle.write("    }\n")

    @staticmethod
    def _map_finish_values(material: MaterialData) -> tuple[float, float, float]:
        roughness = MaterialWriter._clamp_unit(material.roughness, default=1.0)
        specular = MaterialWriter._clamp_unit(material.specular, default=0.0)
        metallic = MaterialWriter._clamp_unit(material.metallic, default=0.0)

        phong = specular * (1.0 - roughness)
        reflection = metallic * 0.5
        return phong, specular, reflection

    @staticmethod
    def _clamp_unit(value: float | None, default: float) -> float:
        if value is None:
            return default
        try:
            value = float(value)
        except (TypeError, ValueError):
            return default
        return max(0.0, min(1.0, value))

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
