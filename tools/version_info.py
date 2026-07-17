"""
Write the Windows version resource PyInstaller stamps into the exe.

Reads the version out of the package so the properties panel can never claim
something different from what the app reports about itself.

Usage: python tools/version_info.py version_info.txt

Written by LJ "HawaiizFynest" Eblacas — Colorado Vista IT Solutions
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dispatch import __app_name__, __author__, __org__, __version__  # noqa: E402

TEMPLATE = """VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({v0}, {v1}, {v2}, 0),
    prodvers=({v0}, {v1}, {v2}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', {org!r}),
          StringStruct('FileDescription', 'Security news triage and drafting desk'),
          StringStruct('FileVersion', '{version}.0'),
          StringStruct('InternalName', {app!r}),
          StringStruct('LegalCopyright', {copyright!r}),
          StringStruct('OriginalFilename', '{app}.exe'),
          StringStruct('ProductName', {app!r}),
          StringStruct('ProductVersion', '{version}'),
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def build() -> str:
    parts = (__version__.split(".") + ["0", "0", "0"])[:3]
    try:
        v0, v1, v2 = (int(p) for p in parts)
    except ValueError:
        raise SystemExit(f"Version {__version__!r} is not three numbers separated by dots.")

    # Hyphen rather than an em dash: the version resource is read back as
    # Latin-1 in places and an em dash shows up as mojibake in the properties
    # panel. Straight ASCII quotes around the handle are fine and survive.
    copyright_line = f"{__author__} - {__org__}"

    return TEMPLATE.format(
        v0=v0,
        v1=v1,
        v2=v2,
        version=__version__,
        app=__app_name__,
        org=__org__,
        copyright=copyright_line,
    )


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("version_info.txt")
    target.write_text(build(), encoding="utf-8")
    print(f"Wrote {target} for {__app_name__} {__version__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
