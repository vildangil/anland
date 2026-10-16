#!/usr/bin/env python3
"""Resolve specifically identified three-way merge conflicts for the 50.5 -> 51.1 port.

This is a one-off *source port* helper, not a general git merge conflict resolver.
Every expected block is checked. Unknown conflicts remain unresolved and fail CI.
"""
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
pattern = re.compile(r"(?ms)^<<<<<<< HEAD\n(.*?)^=======\n(.*?)^>>>>>>> [^\n]+\n")


def select(path, ours, theirs):
    if path == "config.h.meson":
        assert "HAVE_ANLAND" in theirs and "HAVE_NATIVE_BACKEND" in theirs
        return "/* Define if the Anland display backend is enabled */\n#mesondefine HAVE_ANLAND\n\n"
    if path == "meson.options":
        assert "option('anland'," in theirs
        return """option('anland',
  type: 'feature',
  value: 'disabled',
  description: 'Enable the Anland display backend'
)

"""
    if path == "meson.build":
        if "have_anland = get_option" in theirs:
            assert "libgbm_dep" in ours
            return ours.rstrip("\n") + "\n\nhave_anland = get_option('anland').enabled()\n\n"
        if "cdata.set('HAVE_ANLAND'" in theirs:
            return "cdata.set('HAVE_ANLAND', have_anland)\n"
    if path == "src/backends/native/meta-renderer-native.c":
        assert "meta_renderer_native_create_dma_buf_framebuffer" in theirs
        return theirs
    if path == "src/core/meta-context-main.c":
        if "gboolean anland;" in theirs:
            return """#ifdef HAVE_ANLAND
  gboolean anland;
  char *anland_socket;
#endif
"""
        if "create_anland_backend" in theirs:
            return """#ifdef HAVE_ANLAND
  if (context_main->options.anland)
    return create_anland_backend (context, error);
#endif
"""
    raise RuntimeError("Unrecognized conflict in " + path)


expected = {
    "config.h.meson": 1,
    "meson.build": 2,
    "meson.options": 1,
    "src/backends/native/meta-renderer-native.c": 1,
    "src/core/meta-context-main.c": 2,
}

for name, required_count in expected.items():
    file = root / name
    data = file.read_text()
    found = list(pattern.finditer(data))
    if len(found) != required_count:
        raise RuntimeError(f"{name}: expected {required_count} conflicts, got {len(found)}")

    def replace(m):
        return select(name, m.group(1), m.group(2))

    result, count = pattern.subn(replace, data)
    assert count == required_count and "<<<<<<<" not in result
    file.write_text(result)
    print(f"Resolved {count} known three-way conflicts in {name}")

print("Initial Mutter 51.1 Meson/context/renderer conflict resolution complete.")
print("C compilation is still required: this is not a runtime compatibility guarantee.")
