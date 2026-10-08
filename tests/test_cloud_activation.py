import copy
import datetime as dt
import unittest
import tempfile
import json
import subprocess
import sys
from pathlib import Path

from clearparcel.datawatch import aggregate
from clearparcel.datawatch.hybrid_validation import candidate_manifest, validation_receipt
from clearparcel.datawatch.public_projection import sanitize_public_render_state
from clearparcel.datawatch.public_publish import _snapshot_is_superseded


class CloudActivationTests(unittest.TestCase):
    stamp = '2026-10-08T12:00:00+00:00'

    def report(self, stamp=None):
        stamp = stamp or self.stamp
        return {'generated_at': stamp, 'overall': 'ok', 'scope': {'type': 'fleet'},
                'sources': {'a': {'id': 'a', 'checked_at': stamp, 'status': 'ok'}}}

    def test_cloud_only_receipt_needs_no_empty_local_heartbeat(self):
        manifest = candidate_manifest({'sources': [{'id': 'a', 'execution_profiles': ['cloud']}]}, {})
        report = self.report()
        report['runtime_identity'] = manifest['runtime_identity']
        state = aggregate.merge_states({}, report, 'cloud')
        receipt = validation_receipt(manifest, {'cloud': report}, state, sanitize_public_render_state(state))
        self.assertTrue(receipt['passed'], receipt['problems'])
        self.assertEqual(receipt['worker_observations'], {'cloud': self.stamp})
        wrong = copy.deepcopy(state)
        wrong['workers']['local'] = {'last_report_at': self.stamp}
        self.assertFalse(validation_receipt(manifest, {'cloud': report}, wrong,
                                          sanitize_public_render_state(wrong))['passed'])

    def test_retirement_preserves_history_and_blocks_worker_resurrection(self):
        state = aggregate.merge_states({}, self.report(), 'local')
        with self.assertRaises(ValueError):
            aggregate.retire_worker(state, 'local', '2026-10-08T14:00:00+00:00')
        migrated = aggregate.merge_states(state, self.report('2026-10-08T13:00:00+00:00'), 'cloud')
        with self.assertRaises(ValueError):
            aggregate.retire_worker(migrated, 'local', 'invalid')
        retired = aggregate.retire_worker(migrated, 'local', '2026-10-08T14:00:00+00:00')
        self.assertNotIn('local', retired['workers'])
        self.assertEqual(retired['retired_workers']['local']['last_report_at'], self.stamp)
        self.assertEqual(retired['sources'], migrated['sources'])
        self.assertEqual(aggregate.merge_states(retired, self.report(), 'local'), retired)
        with self.assertRaises(ValueError):
            aggregate.merge_states(retired, self.report('2026-10-08T15:00:00+00:00'), 'local')
        fresh = aggregate.with_freshness(retired, now=dt.datetime.fromisoformat('2026-10-08T14:00:00+00:00'))
        self.assertEqual(fresh['stale_workers'], 0)

    def test_public_guard_accepts_only_explicit_newer_worker_retirement(self):
        state = aggregate.merge_states({}, self.report(), 'local')
        migrated = aggregate.merge_states(state, self.report('2026-10-08T13:00:00+00:00'), 'cloud')
        public = sanitize_public_render_state(migrated)
        retired = aggregate.retire_worker(migrated, 'local', '2026-10-08T14:00:00+00:00')
        candidate = sanitize_public_render_state(retired)
        self.assertEqual(candidate['retired_workers']['local']['last_report_at'], self.stamp)
        self.assertFalse(_snapshot_is_superseded(candidate, public))
        absent = copy.deepcopy(candidate)
        absent['retired_workers'] = {}
        self.assertTrue(_snapshot_is_superseded(absent, public))
        stale = copy.deepcopy(candidate)
        stale['retired_workers']['local']['retired_at'] = self.stamp
        self.assertTrue(_snapshot_is_superseded(stale, public))
        self.assertTrue(_snapshot_is_superseded(public, candidate))

    def test_retirement_cas_retry_preserves_concurrent_cloud_report(self):
        from clearparcel.datawatch.storage import StorageConflictError
        state = aggregate.merge_states({}, self.report(), 'local')
        migrated = aggregate.merge_states(state, self.report('2026-10-08T13:00:00+00:00'), 'cloud')
        concurrent = self.report('2026-10-08T13:30:00+00:00')
        concurrent['sources']['b'] = {'id': 'b', 'status': 'ok', 'checked_at': concurrent['generated_at']}

        class Storage:
            def __init__(self):
                self.state = migrated
                self.version = 1

            def download_versioned(self, name, path):
                aggregate.save_json(path, self.state)
                return True, self.version

            def upload_if_version(self, name, path, version):
                if self.version == 1:
                    self.state = aggregate.merge_states(self.state, concurrent, 'cloud')
                    self.version = 2
                    raise StorageConflictError('concurrent cloud writer')
                self.state = aggregate.load_json(path)

        storage = Storage()
        with tempfile.TemporaryDirectory() as td:
            result = aggregate.publish_worker_retirement(storage, 'aggregate.json', 'local',
                        '2026-10-08T14:00:00+00:00', Path(td))
        self.assertEqual(set(result['sources']), {'a', 'b'})
        self.assertEqual(result['workers']['cloud']['last_report_at'], concurrent['generated_at'])
        self.assertNotIn('local', result['workers'])

    def test_offline_cli_receipt_and_retirement_use_no_local_report(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            paths = Path(td)
            config = {'sources': [{'id': 'a', 'execution_profiles': ['cloud']}]}
            config_path = paths / 'config.json'
            aggregate.save_json(config_path, config)
            from clearparcel.datawatch.watch import load_config
            manifest = candidate_manifest(load_config(config_path))
            report = self.report()
            report['runtime_identity'] = manifest['runtime_identity']
            state = aggregate.merge_states({}, self.report('2026-10-08T11:00:00+00:00'), 'local')
            state = aggregate.merge_states(state, report, 'cloud')
            aggregate.save_json(paths / 'base.json', state)
            retired = subprocess.run([sys.executable, '-m', 'clearparcel.datawatch', 'worker-retire',
                '--base', str(paths / 'base.json'), '--worker', 'local', '--at',
                '2026-10-08T13:00:00+00:00', '--output', str(paths / 'aggregate.json')],
                cwd=root, capture_output=True, text=True)
            self.assertEqual(retired.returncode, 0, retired.stderr)
            aggregate.save_json(paths / 'cloud.json', report)
            aggregate.save_json(paths / 'public.json', sanitize_public_render_state(
                aggregate.load_json(paths / 'aggregate.json')))
            result = subprocess.run([sys.executable, 'scripts/validate_hybrid_observations.py',
                '--config', str(config_path), '--cloud', str(paths / 'cloud.json'),
                '--aggregate', str(paths / 'aggregate.json'), '--public', str(paths / 'public.json'),
                '--output', str(paths / 'receipt.json')], cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(json.loads((paths / 'receipt.json').read_text(encoding='utf-8'))['passed'])


if __name__ == '__main__':
    unittest.main()
