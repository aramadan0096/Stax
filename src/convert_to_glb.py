# -*- coding: utf-8 -*-
"""Blender conversion script for StaX.

Invoke via:
  blender --background --python convert_to_glb.py -- <input_file> <output_file>

This script mirrors the reference implementation used in tests/glb_converter and
is copied into the production tree so the tests directory can be removed safely.
"""

from __future__ import print_function

import sys
import os
import traceback
import re

try:
    import bpy
except Exception:
    print("This script must be executed inside Blender (bpy module missing).")
    raise


def usage_and_exit():
    print("Usage: blender --background --python convert_to_glb.py -- <input_path> <output_path>")
    sys.exit(1)


def dump_operator_info():
    try:
        print("Operator info for bpy.ops.export_scene.gltf:")
        print(bpy.ops.export_scene.gltf)
    except Exception as exc:  # pylint: disable=broad-except
        print("Could not print operator info:", exc)


def try_iterative_export(output_path, kwargs):
    """Attempt export removing unsupported keyword arguments when necessary."""
    attempt = 0
    active_kwargs = dict(kwargs)
    removed = []

    while True:
        attempt += 1
        try:
            print("Export attempt #%d using %d kwargs" % (attempt, len(active_kwargs)))
            bpy.ops.export_scene.gltf(**active_kwargs)
            print("Export succeeded on attempt #%d" % attempt)
            if removed:
                print("Removed unsupported kwargs during retries:", removed)
            return True
        except TypeError as type_err:
            message = str(type_err)
            print("TypeError while exporting:", message)
            match = (re.search(r'keyword "?\'?([A-Za-z0-9_]+)\'?"? unrecognized', message)
                     or re.search(r'keyword "([^"]+)" unrecognized', message)
                     or re.search(r"keyword '([^']+)' unrecognized", message))
            if match:
                bad_kw = match.group(1)
                if bad_kw in active_kwargs:
                    print("Removing unsupported kw '%s' and retrying." % bad_kw)
                    removed.append(bad_kw)
                    del active_kwargs[bad_kw]
                    if not active_kwargs:
                        print("All kwargs removed; aborting.")
                        break
                    continue
                print("Keyword '%s' reported but not present; aborting." % bad_kw)
                break
            else:
                print("Could not parse unsupported keyword from message; aborting.")
                break
        except Exception as exc:  # pylint: disable=broad-except
            print("Unexpected exception during export:", exc)
            traceback.print_exc()
            return False

    return False


def main():
    argv = sys.argv
    if "--" in argv:
        idx = argv.index("--")
        cli_args = argv[idx + 1:]
    else:
        cli_args = []

    if len(cli_args) < 2:
        usage_and_exit()

    input_path = os.path.abspath(cli_args[0])
    output_path = os.path.abspath(cli_args[1])

    if not os.path.exists(input_path):
        print("Input file not found:", input_path)
        sys.exit(2)

    in_ext = os.path.splitext(input_path)[1].lower()

    bpy.ops.wm.read_factory_settings(use_empty=True)

    try:
        if in_ext == '.fbx':
            print("Importing FBX:", input_path)
            bpy.ops.import_scene.fbx(filepath=input_path)
        elif in_ext == '.obj':
            print("Importing OBJ:", input_path)
            bpy.ops.import_scene.obj(filepath=input_path)
        elif in_ext in ('.abc', '.alembic'):
            print("Importing Alembic:", input_path)
            bpy.ops.wm.alembic_import(filepath=input_path)
        elif in_ext in ('.glb', '.gltf'):
            print("Input already glTF/GLB; attempting import.")
            try:
                bpy.ops.import_scene.gltf(filepath=input_path)
            except Exception:  # pylint: disable=broad-except
                import shutil
                print("Import failed, copying file to destination instead.")
                shutil.copy2(input_path, output_path)
                print("Copied", input_path, "->", output_path)
                return
        else:
            print("Unsupported input extension:", in_ext)
            sys.exit(3)

        out_root, out_ext = os.path.splitext(output_path)
        if out_ext.lower() not in ('.glb', '.gltf'):
            output_path = out_root + '.glb'

        print("Exporting GLB to:", output_path)

        export_kwargs = dict(
            filepath=output_path,
            export_format='GLB',
            export_texcoords=True,
            export_normals=True,
            export_materials='EXPORT',
            export_cameras=True,
            export_animations=True,
            export_apply=True,
            export_yup=True,
            export_tangents=False,
            export_draco_mesh_compression_enable=False
        )

        success = try_iterative_export(output_path, export_kwargs)
        if not success:
            print("Iterative export failed; trying minimal fallback.")
            try:
                bpy.ops.export_scene.gltf(filepath=output_path, export_format='GLB')
                print("Fallback export completed:", output_path)
                success = True
            except Exception:  # pylint: disable=broad-except
                print("Fallback export failed.")
                traceback.print_exc()
                dump_operator_info()
                sys.exit(4)

        if success:
            print("Export completed successfully:", output_path)
        else:
            print("Export did not complete.")
            sys.exit(5)

    except Exception as exc:  # pylint: disable=broad-except
        print("Conversion error:", exc)
        traceback.print_exc()
        sys.exit(6)


if __name__ == '__main__':
    main()
