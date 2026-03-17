from __future__ import annotations

from typing import Iterable, TextIO

from .export_types import MaterialData


class MaterialWriter:
    """
    Writes minimal Phase 2 material declarations.

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
    def write_material_declarations(f: TextIO, material_records: Iterable[MaterialData]) -> None:
        material_list = [mat for mat in material_records if mat is not None]

        if not material_list:
            return

        f.write("// ------------------------------------------------------------\n")
        f.write("// Material declarations\n")
        f.write("// ------------------------------------------------------------\n")

        for material in material_list:
            MaterialWriter.write_material_declaration(f, material)
            f.write("\n")

    @staticmethod
    def write_material_declaration(f: TextIO, material: MaterialData) -> None:
        if not material.is_supported:
            MaterialWriter._write_fallback_material(f, material)
            return

        if material.image_texture is not None:
            MaterialWriter._write_image_texture_material(f, material)
            return

        if material.base_color is not None:
            MaterialWriter._write_solid_color_material(f, material)
            return

        MaterialWriter._write_fallback_material(f, material)

    @staticmethod
    def _write_solid_color_material(f: TextIO, material: MaterialData) -> None:
        r, g, b = material.base_color
        f.write(f"#declare {material.export_name} = texture {{\n")
        f.write("    pigment {\n")
        f.write(
            f"        color srgb <{MaterialFormatters.float(r)}, {MaterialFormatters.float(g)}, {MaterialFormatters.float(b)}>\n"
        )
        f.write("    }\n")
        f.write("    finish {\n")
        f.write("        ambient 0\n")
        f.write("        diffuse 0.8\n")
        f.write("        specular 0\n")
        f.write("        roughness 1\n")
        f.write("    }\n")
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
        f.write("    finish {\n")
        f.write("        ambient 1\n")
        f.write("        diffuse 0.8\n")
        f.write("        specular 0\n")
        f.write("        roughness 1\n")
        f.write("    }\n")
        f.write("}\n")


    @staticmethod
    def _write_fallback_material(f: TextIO, material: MaterialData) -> None:
        if material.warning:
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
