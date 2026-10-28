import base64
from pathlib import Path
import tempfile
import threading
import time
import unittest
from agent.tools import Tools


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cancel = threading.Event()
        self.tools = Tools(self.root, self.cancel, lambda p: True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_read_paging(self):
        (self.root / 'a').write_text('a\nb\nc\nd\n')
        r = self.tools.read('a', offset=2, limit=2)
        self.assertEqual(r['text'], '   2 | b\n   3 | c')
        self.assertEqual(r['remaining_lines'], 1)
        self.assertEqual(r['next_offset'], 4)

    def test_read_image_block(self):
        (self.root / 'a.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aF2kAAAAASUVORK5CYII='))
        r = self.tools.read('a.png')
        self.assertEqual(r['content'][0]['type'], 'image')
        self.assertNotIn('text', r['content'][0])

    def test_unique_edit_preserves_rest(self):
        (self.root / 'a').write_text('alpha=1\nbeta=1\n')
        self.assertFalse(self.tools.call('edit', {'path':'a','old':'1','new':'2'})['ok'])
        self.assertFalse(self.tools.call('edit', {'path':'a','old':'missing','new':'2'})['ok'])
        self.tools.edit('a','beta=1','beta=2')
        self.assertEqual((self.root / 'a').read_text(), 'alpha=1\nbeta=2\n')

    def test_atomic_write_parents_and_line_counts(self):
        self.tools.write('new/nested/a', 'a\nb\n')
        r = self.tools.write('new/nested/a', 'c\n')
        self.assertEqual((r['old_lines'], r['new_lines']), (2, 1))
        self.assertEqual(list((self.root / 'new/nested').glob('.agent-write-*')), [])

    def test_denied_write(self):
        t = Tools(self.root, approve=lambda _: False)
        self.assertFalse(t.call('write', {'path':'a','content':'x'})['ok'])
        self.assertFalse((self.root / 'a').exists())

    def test_concurrent_change_is_not_overwritten(self):
        p = self.root / 'a'
        p.write_text('old')
        def approve(proposal):
            p.write_text('other editor')
            return True
        t = Tools(self.root, approve=approve)
        self.assertFalse(t.call('edit', {'path':'a','old':'old','new':'new'})['ok'])
        self.assertEqual(p.read_text(), 'other editor')

    def test_path_traversal_and_symlink(self):
        self.assertFalse(self.tools.call('read', {'path':'../outside'})['ok'])
        (self.root / 'link').symlink_to('/etc')
        self.assertFalse(self.tools.call('read', {'path':'link/passwd'})['ok'])

    def test_bash_failure_and_truncation(self):
        r = self.tools.bash("python3 -c 'import sys; print(\"x\"*20000); print(\"error\", file=sys.stderr); sys.exit(3)'")
        self.assertEqual(r['exit_code'],3)
        self.assertTrue(r['truncated'])
        self.assertIn('error',r['stderr'])
        self.assertLessEqual(len(r['stdout']),16000)

    def test_bash_timeout(self):
        r = self.tools.bash('sleep 10', timeout=.15)
        self.assertEqual(r['reason'],'timeout')
        self.assertLess(r['seconds'],2)

    def test_bash_cancel(self):
        threading.Timer(.2,self.cancel.set).start()
        r = self.tools.bash('sleep 10',timeout=15)
        self.assertEqual(r['reason'],'cancelled')
        self.assertLess(r['seconds'],2)


if __name__ == '__main__':
    unittest.main()
