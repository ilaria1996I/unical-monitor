import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import monitor as m


def page(extra='', noise=''):
    return '<html><nav>' + noise + '</nav><div class="main-body"><div class="py-5"><div class="container"><div class="row"><div class="col-lg-8"><h3>Sostegno 2025/26</h3><p>' + ('Avviso importante. ' * 30) + '</p><div class="accordion-collapse collapse">' + extra + '</div><script>' + noise + '</script></div></div></div></div></div></html>'


class MonitorTests(unittest.TestCase):
    def test_dynamic_noise_ignored(self):
        self.assertEqual(m.extract(page(noise='123')), m.extract(page(noise='999')))

    def test_collapsed_notice_detected(self):
        self.assertNotEqual(m.extract(page()), m.extract(page('Nuovo scorrimento')))

    def test_pdf_target_change_detected(self):
        self.assertNotEqual(m.extract(page('<a href="/a.pdf">Graduatoria</a>')),
                            m.extract(page('<a href="/b.pdf">Graduatoria</a>')))

    def test_tracking_and_fragment_ignored(self):
        self.assertEqual(m.canonical_link('/a.pdf?utm_source=x#top'), m.canonical_link('/a.pdf'))
        self.assertNotEqual(m.canonical_link('/a.pdf?v=1'), m.canonical_link('/a.pdf?v=2'))

    def test_bad_page_rejected(self):
        with self.assertRaises(m.MonitorError):
            m.extract('<html>Maintenance</html>')

    def test_persistence_and_delivery_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'state.json'
            sent = []
            m.run(state, fetch=lambda: page(), send=sent.append, confirm_delay=0)
            initial = state.read_bytes()
            m.run(state, fetch=lambda: page(), send=sent.append, confirm_delay=0)
            self.assertEqual(len(sent), 1)
            self.assertEqual(state.read_bytes(), initial)
            def failed(message):
                raise m.MonitorError('Invio fallito')
            with self.assertRaises(m.MonitorError):
                m.run(state, fetch=lambda: page('Nuovo'), send=failed, confirm_delay=0)
            self.assertEqual(state.read_bytes(), initial)
            m.run(state, fetch=lambda: page('Nuovo'), send=sent.append, confirm_delay=0)
            self.assertEqual(len(sent), 2)
            self.assertNotEqual(state.read_bytes(), initial)

    def test_unstable_page_preserves_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'state.json'
            m.run(state, fetch=lambda: page(), send=lambda _: None)
            initial = state.read_bytes()
            pages = iter([page('Nuovo'), page()])
            with self.assertRaises(m.MonitorError):
                m.run(state, fetch=lambda: next(pages), send=lambda _: self.fail('unexpected send'), confirm_delay=0)
            self.assertEqual(state.read_bytes(), initial)

    def test_corrupt_state_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'state.json'
            state.write_text('{}')
            with self.assertRaises(m.MonitorError):
                m.load_state(state)

    def test_telegram_error_redacted(self):
        with patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test-secret', 'TELEGRAM_CHAT_ID': 'test-chat'}):
            with patch('monitor.urlopen', side_effect=Exception('test-secret test-chat')):
                with self.assertRaises(m.MonitorError) as error:
                    m.send_telegram('Test')
                self.assertNotIn('test-secret', str(error.exception))
                self.assertNotIn('test-chat', str(error.exception))


if __name__ == '__main__':
    unittest.main()
