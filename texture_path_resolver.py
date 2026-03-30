from __future__ import annotations

import os
import shutil
from dataclasses import replace
from pathlib import Path

from .export_types import ExportContext, ExportOptions, ImageTextureData, MaterialData


class TexturePathResolver:
    @staticmethod
    def resolve(
        source_path: str,
        output_pov_path: str,
        mode: str = "RELATIVE",  # ABSOLUTE | RELATIVE | COPY
        copy_enabled: bool = False,
        copy_subdir: str = "textures",
    ) -> tuple[str, bool]:
        if not source_path:
            return "", False

        source = Path(source_path).resolve()
        pov_path = Path(output_pov_path).resolve()
        pov_dir = pov_path.parent

        if copy_enabled:
            mode = "COPY"

        if mode == "ABSOLUTE":
            return str(source), False

        if mode == "RELATIVE":
            try:
                rel = os.path.relpath(source, pov_dir)
                return rel, False
            except ValueError:
                return str(source), False

        if mode == "COPY":
            target_dir = pov_dir / copy_subdir
            target_dir.mkdir(parents=True, exist_ok=True)

            target_path = target_dir / source.name

            try:
                shutil.copy2(source, target_path)
            except Exception:
                return str(source), False

            rel = os.path.relpath(target_path, pov_dir)
            return rel, True

        return str(source), False

    @staticmethod
    def resolve_material_texture_paths(
        material: MaterialData,
        export_ctx: ExportContext,
        export_options: ExportOptions,
    ) -> MaterialData:
        if material.image_texture is None:
            return material

        image = material.image_texture

        source_path = image.filepath_resolved or image.filepath_raw
        if not source_path:
            return material

        emitted_path, _copied = TexturePathResolver.resolve(
            source_path=source_path,
            output_pov_path=export_ctx.filepath,
            mode=export_options.texture_path_mode,
            copy_enabled=export_options.copy_texture_assets,
            copy_subdir=export_options.texture_copy_subdir,
        )

        updated_image = replace(image, emitted_path=emitted_path)
        return replace(material, image_texture=updated_image)
