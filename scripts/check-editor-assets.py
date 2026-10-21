#!/usr/bin/env python3
"""Regression tests for the release artifact trust boundary (no external dependencies)."""

from pathlib import Path
import runpy
import tempfile
import unittest

install = runpy.run_path(str(Path(__file__).with_name('install-editor-assets.py')))['install']


class EditorAssetsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'artifact'
        self.source.mkdir()
        (self.source / 'index.html').write_text('<html>editor</html>')
        (self.source / 'app').mkdir()
        (self.source / 'app/app.js').write_text('editor()')
        self.destination = self.root / 'checkout/dist/static'
        self.plugin = self.root / 'checkout/lib.php'
        self.plugin.parent.mkdir()
        self.plugin.write_text('trusted plugin')

    def test_copies_only_into_static_directory(self):
        (self.source / 'app/payload.bin.zst').write_bytes(b'compressed static data')
        # Locale infixes are data, including Polish, which shares Perl's `.pl`.
        (self.source / 'app/messages.pl.json').write_text('{}')
        (self.source / 'app/messages.pl.js').write_text('var messages = {};')
        install(self.source, self.destination)
        self.assertEqual((self.destination / 'app/app.js').read_text(), 'editor()')
        self.assertEqual(self.plugin.read_text(), 'trusted plugin')

    def test_rejects_server_code_and_configuration_before_copying(self):
        for name in ('lib.php', 'LIB.PHP', 'shell.php.png', 'shell.phtml', '.htaccess', '.user.ini', 'run.cgi', 'run.cgi.js', 'run.py', 'run.sh'):
            with self.subTest(name=name):
                malicious = self.source / name
                malicious.write_text('untrusted')
                with self.assertRaises(ValueError):
                    install(self.source, self.destination)
                self.assertFalse(self.destination.exists())
                self.assertEqual(self.plugin.read_text(), 'trusted plugin')
                malicious.unlink()

    def test_rejects_script_handler_infixes(self):
        # Apache mod_mime applies an AddHandler mapping to any extension in the
        # name, so run.py.js runs as CGI wherever `.py` is mapped to cgi-script.
        for name, content in (('run.py.js', 'untrusted'), ('run.rb.json', 'untrusted'),
                              ('run.sh.js', 'untrusted'), ('run.fcgi.js', 'untrusted'),
                              ('run.pl.js', '#!/usr/bin/perl'), ('RUN.PL.JSON', '#!/usr/bin/perl')):
            with self.subTest(name=name):
                malicious = self.source / name
                malicious.write_text(content)
                with self.assertRaises(ValueError):
                    install(self.source, self.destination)
                self.assertFalse(self.destination.exists())
                malicious.unlink()

    def test_rejects_file_and_directory_symlinks(self):
        for target in (self.plugin, self.plugin.parent):
            with self.subTest(target=target):
                link = self.source / 'app/link.js'
                link.symlink_to(target)
                with self.assertRaises(ValueError):
                    install(self.source, self.destination)
                link.unlink()

    def test_rejects_missing_bundle_and_existing_destination(self):
        (self.source / 'index.html').unlink()
        with self.assertRaises(ValueError):
            install(self.source, self.destination)
        (self.source / 'index.html').write_text('editor')
        self.destination.mkdir(parents=True)
        with self.assertRaises(FileExistsError):
            install(self.source, self.destination)


if __name__ == '__main__':
    unittest.main()
