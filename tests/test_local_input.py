"""Reject explicit remote spellings before filesystem metadata/open calls."""
import importlib.util
from pathlib import Path
import stat
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('local_subject', ROOT/'http_age_explain.py')
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


class LocalInputTests(unittest.TestCase):
    def test_remote_spelling_rejected_before_filesystem_access(self):
        paths = ['https://example.invalid/capture.json', 'file:///capture.json',
                 '//host/share/capture.json', r'\\host\share\capture.json',
                 r'/\host\share\capture.json', r'\/host/share/capture.json',
                 r'\\?\C:\capture.json', r'\\.\device', 'ssh:remote.json']
        for path in paths:
            with self.subTest(path=path):
                with mock.patch.object(subject.os, 'stat', return_value=SimpleNamespace(st_mode=stat.S_IFREG)) as metadata, \
                     mock.patch.object(subject.os, 'open', side_effect=OSError('sentinel')) as opener:
                    with self.assertRaises(subject.InputError):
                        subject.load_capture(path)
                    metadata.assert_not_called()
                    opener.assert_not_called()

    def test_named_local_and_drive_spellings_reach_filesystem_check(self):
        for path in ['capture.json', './capture.json', '/tmp/capture.json',
                     r'C:\capture.json', 'C:/capture.json', 'C:capture.json',
                     Path('capture.json')]:
            with self.subTest(path=path):
                with mock.patch.object(subject.os, 'stat', side_effect=OSError('sentinel')) as metadata:
                    with self.assertRaises(subject.InputError):
                        subject.load_capture(path)
                    metadata.assert_called_once_with(path)
