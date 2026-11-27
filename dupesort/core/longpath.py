"""Long paths on Windows.

Windows programs can only use paths up to 259 characters unless they write them in the
extended form "\\\\?\\C:\\..." or "\\\\?\\UNC\\server\\share\\...", which allows about 32,000.
Moving a file into "_Duplicates" (or a dated folder) adds to its path, so a file that was
just under the limit ends up over it and Windows answers "cannot find the path specified".
``lp`` turns any path into the extended form on Windows; elsewhere it changes nothing.
"""

from __future__ import annotations

import ntpath
import os
import sys

_PREFIX = "\\\\?\\"


def lp(path) -> str:
    """``path`` as a string Windows accepts at any length (unchanged on other systems)."""
    s = os.fspath(path)
    if sys.platform != "win32" or s.startswith(_PREFIX):
        return s
    if not ntpath.isabs(s):
        s = ntpath.join(os.getcwd(), s)
    s = ntpath.normpath(s)  # the extended form needs backslashes and no "." or ".."
    if s.startswith("\\\\"):  # network share: \\server\share\... -> \\?\UNC\server\share\...
        return _PREFIX + "UNC\\" + s[2:]
    return _PREFIX + s


def unlp(path: str) -> str:
    """The normal form of a path ``lp`` made (for showing and storing)."""
    if path.startswith(_PREFIX + "UNC\\"):
        return "\\\\" + path[len(_PREFIX) + 4:]
    if path.startswith(_PREFIX):
        return path[len(_PREFIX):]
    return path


def exists(path) -> bool:
    return os.path.exists(lp(path))


def is_dir(path) -> bool:
    return os.path.isdir(lp(path))
