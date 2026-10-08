import json
import tempfile
import unittest
from pathlib import Path

from scripts.import_public_development_snapshot import prepare_snapshot


class PublicDevelopmentSnapshotTests(unittest.TestCase):
    def test_replay_preserves_observation_clocks_and_disables_polling(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'public.json'
            stamp = '2026-10-07T12:00:00+00:00'
            source.write_text(json.dumps({'generated_at': stamp, 'public_published_at': stamp,
                'sources': {'a': {'id': 'a', 'status': 'ok', 'checked_at': stamp}},
                'workers': {'cloud': {'last_report_at': stamp}}}), encoding='utf-8')
            output = prepare_snapshot(source, root / 'replay')
            state = json.loads((output / 'objects/aggregate-state.json').read_text())
            self.assertEqual(state['generated_at'], stamp)
            self.assertEqual(state['sources']['a']['checked_at'], stamp)
            config = json.loads((output / 'config.json').read_text())
            self.assertEqual(config['sources'], [])
            self.assertFalse(config['public_dashboard']['internet_exposure'])
            with self.assertRaises(FileExistsError):
                prepare_snapshot(source, output)

    def test_operational_input_rejected_before_output_created(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'private.json'
            source.write_text(json.dumps({'sources': {'a': {'url': 'https://example.test'}}}))
            with self.assertRaises(RuntimeError):
                prepare_snapshot(source, root / 'replay')
            self.assertFalse((root / 'replay').exists())

    def test_missing_observation_clock_is_not_invented(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'empty.json'
            source.write_text(json.dumps({'sources': {'a': {'status': 'ok'}}}))
            with self.assertRaises(ValueError):
                prepare_snapshot(source, root / 'replay')
