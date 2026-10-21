#!/usr/bin/env python3
"""Validate untrusted build output before copying it into a clean release checkout."""

import os
from pathlib import Path
import re
import shutil
import stat
import sys

# Static formats shipped by the editor; new formats require an explicit review.
STATIC_SUFFIXES = set('''
.appcache .bak .css .csv .dtd .eot .gif .gz .html .ico .jpeg .jpg .js .json
.map .md .mjs .mp3 .mp4 .mts .ogg .otf .pdf .png .po .sdf .svg .swf .ts
.ttf .txt .wasm .wav .webm .webp .woff .woff2 .xap .xml .xsd .zip .zst
'''.split())
# Apache mod_mime applies AddHandler/AddType mappings to every extension in a name,
# so shell.php.png or run.py.js can execute where those extensions are mapped.
SERVER_SUFFIX = re.compile(r'\.(?:php\d*|phtml|pht|phar|shtml|cgi|fcgi|py|rb|sh)(?:\.|$)', re.I)
# `.pl` is also the Polish locale code (messages.pl.json). A CGI script needs an
# interpreter line, so a `.pl` infix is rejected only on a file that starts with one.
PERL_SUFFIX = re.compile(r'\.pl(?:\.|$)', re.I)


def is_server_script(path: Path) -> bool:
    """Return whether a file name could be dispatched to a server-side handler."""
    if SERVER_SUFFIX.search(path.name):
        return True
    if PERL_SUFFIX.search(path.name):
        with path.open('rb') as handle:
            return handle.read(2) == b'#!'
    return False


def install(source: Path, destination: Path) -> None:
    """Reject links, server code and configuration files before copying any assets."""
    if source.is_symlink() or not source.is_dir():
        raise ValueError('Editor artifact must be a directory')
    for root, dirs, files in os.walk(source, followlinks=False):
        for name in dirs + files:
            path = Path(root) / name
            mode = path.lstat().st_mode
            if name.startswith('.') or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError(f'Unsafe editor asset: {path}')
            if stat.S_ISREG(mode) and (
                is_server_script(path)
                or (path.suffix.lower() not in STATIC_SUFFIXES and name not in {'LICENSE', 'mimetype'})
            ):
                raise ValueError(f'Non-static editor asset: {path}')
    if not (source / 'index.html').is_file() or not any(
        (source / name).is_dir() for name in ('app', 'libs', 'files')
    ):
        raise ValueError('Editor artifact is missing its entry page or assets')
    # Never merge untrusted files with an existing tree, or copy anything outside dist/static.
    shutil.copytree(source, destination)


if __name__ == '__main__':
    install(Path(sys.argv[1]), Path('dist/static'))
