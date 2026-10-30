"""Windows bridge: state transitions, approvals, auth, quota, graph provenance and local safety."""
import base64
import json
import os
import sqlite3
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import codex_bridge as bridge


class BridgeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / 'agent.sqlite3'
        self.settings = {
            'GIT_ALLOWED_REPOS': 'ITAM=gyangho/ITAM;LKH_MCP=gyangho/LKH_MCP',
            'CODEX_AGENT_ENABLED': True,
            'CODEX_MAX_RUNS_PER_DAY': 30,
        }
        patches = [patch.object(bridge.settings_store, 'get', side_effect=lambda k: self.settings[k]),
                   patch.object(bridge.settings_store, '_connect', side_effect=lambda: sqlite3.connect(self.db))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        e = patch.dict(os.environ, {'CODEX_AGENT_TOKEN': 'X'*48})
        e.start(); self.addCleanup(e.stop)

    def enqueue(self, kind='verify'):
        return bridge.enqueue('ITAM', 'main', 'a'*40, kind=kind,
                              instructions='Investigate and fix the failing test' if kind == 'fix' else 'Run tests')

    def test_queue_and_completion(self):
        job = self.enqueue()
        self.assertEqual(job['state'], 'queued')
        self.assertEqual(bridge.list_tasks()['tasks'][0]['state'], 'queued')
        claim = bridge.claim('win-01', ['ITAM'])
        self.assertEqual(claim['job']['id'], job['id'])
        self.assertFalse('lease' in bridge.get_task(job['id']))
        with self.assertRaises(PermissionError):
            bridge.complete(job['id'], 'bad', 'win-01', True, 'Passed', '')
        result = bridge.complete(job['id'], claim['lease'], 'win-01', True, 'Passed', '')
        self.assertEqual(result['state'], 'completed')
        self.assertEqual(bridge.get_task(job['id'])['report'], 'Passed')
        with self.assertRaises(PermissionError):
            bridge.complete(job['id'], claim['lease'], 'win-01', True, 'Again')

    def test_fix_requires_admin_approval(self):
        job = self.enqueue('fix')
        self.assertEqual(job['state'], 'pending_approval')
        self.assertIsNone(bridge.claim('win-01', ['ITAM'])['job'])
        decision = bridge.decide(job['id'], 'approve', 'admin')
        self.assertEqual(decision['state'], 'queued')
        self.assertEqual(bridge.claim('win-01', ['ITAM'])['job']['id'], job['id'])

    def test_cancel_prevents_execution(self):
        job = self.enqueue()
        bridge.decide(job['id'], 'cancel', 'admin')
        self.assertIsNone(bridge.claim('win-01', ['ITAM'])['job'])

    def test_quota_and_invalid_job(self):
        self.settings['CODEX_MAX_RUNS_PER_DAY'] = 1
        self.enqueue()
        self.assertTrue(bridge.claim('win-01', ['ITAM'])['job'])
        self.enqueue()
        self.assertIsNone(bridge.claim('win-01', ['ITAM'])['job'])
        with self.assertRaises(ValueError):
            bridge.enqueue('ITAM', 'main;del', 'a'*40)
        with self.assertRaises(ValueError):
            bridge.enqueue('ITAM', 'main', 'a'*39)
        with self.assertRaises(ValueError):
            bridge.enqueue('NOPE', 'main', 'a'*40)

    def test_graph_provenance_and_lookup(self):
        graph = {'nodes': [{'id': 'a', 'label': 'auth'}, {'id': 'b', 'label': 'login'}],
                 'links': [{'source': 'a', 'target': 'b', 'relation': 'calls'}]}
        encoded = base64.b64encode(zlib.compress(json.dumps(graph).encode())).decode()
        job = self.enqueue('graphify')
        claimed = bridge.claim('win-01', ['ITAM'])
        bridge.complete(job['id'], claimed['lease'], 'win-01', True, 'updated', graph_base64=encoded)
        listing = bridge.graph_list()['projects']
        self.assertEqual(listing[0]['commit_sha'], 'a'*40)
        self.assertEqual(bridge.graph_query('ITAM', 'auth')['matches'][0]['id'], 'a')
        self.assertEqual(bridge.graph_path('ITAM', 'a', 'b')['path'], ['a','b'])
        self.assertEqual(len(bridge.graph_neighbors('ITAM', 'a')['edges']), 1)

    def test_graph_upload_only_graphify(self):
        raw = base64.b64encode(zlib.compress(b'{"nodes":[],"links":[]}')).decode()
        job = self.enqueue('verify')
        claim = bridge.claim('win-01', ['ITAM'])
        with self.assertRaises(ValueError):
            bridge.complete(job['id'], claim['lease'], 'win-01', True, 'bad', graph_base64=raw)

    def test_bearer_token(self):
        self.assertTrue(bridge.check_agent_token('Bearer '+'X'*48))
        self.assertFalse(bridge.check_agent_token('Bearer '+'Y'*48))
        self.assertFalse(bridge.check_agent_token(''))


class WindowsAgentTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root))
        from windows_agent import agent
        self.agent = agent

    def test_safe_env_preserves_windows_system_drive_without_secrets(self):
        # MXC needs host SystemDrive to start Windows child commands.
        with patch.dict(os.environ, {
            'SystemDrive': 'C:',
            'CODEX_AGENT_TOKEN': 'never-expose-token',
            'LKH_CODEX_AGENT_TOKEN': 'never-expose-agent-token',
        }):
            env = self.agent.safe_env()
        self.assertEqual(env.get('SystemDrive'), 'C:')
        self.assertNotIn('CODEX_AGENT_TOKEN', env)
        self.assertNotIn('LKH_CODEX_AGENT_TOKEN', env)

    def test_safe_env_restores_missing_systemdrive_from_systemroot(self):
        with patch.object(self.agent.sys, "platform", "win32"):
            with patch.dict(os.environ, {
                'SystemRoot': r'D:\\Windows',
                'WINDIR': r'D:\\Windows',
                'CODEX_AGENT_TOKEN': 'private-token',
            }, clear=True):
                env = self.agent.safe_env()
        self.assertEqual(env['SystemDrive'], 'D:')
        self.assertEqual(env['SystemRoot'], r'D:\\Windows')
        self.assertNotIn('CODEX_AGENT_TOKEN', env)

    def test_safe_env_uses_windir_if_systemroot_is_missing(self):
        with patch.object(self.agent.sys, "platform", "win32"):
            with patch.dict(os.environ, {'WINDIR': r'E:\\Windows'}, clear=True):
                self.assertEqual(self.agent.safe_env()['SystemDrive'], 'E:')

    def test_safe_env_rejects_missing_windows_roots(self):
        with patch.object(self.agent.sys, "platform", "win32"):
            with patch.dict(os.environ, {'SystemDrive': ''}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "SystemDrive unavailable"):
                    self.agent.safe_env()

    def test_safe_env_recovers_from_invalid_systemdrive(self):
        with patch.object(self.agent.sys, "platform", "win32"):
            with patch.dict(os.environ, {
                'SystemDrive': r'Z:\\Windows',
                'SystemRoot': r'D:\\Windows',
            }, clear=True):
                self.assertEqual(self.agent.safe_env()['SystemDrive'], 'D:')

    def test_safe_pull_rejects_sha_mismatch(self):
        git_results = iter(['', 'b'*40])
        with patch.object(self.agent, 'checked_repo'), patch.object(self.agent, 'git', side_effect=lambda *a, **kw: next(git_results)):
            with self.assertRaises(RuntimeError):
                self.agent.safe_pull(Path('C:/repo'), 'gyangho/ITAM', 'main', 'a'*40)

    def test_windows_agent_no_local_mutation_on_invalid_mapping(self):
        with patch.object(self.agent, 'safe_pull', side_effect=AssertionError('must not touch files')):
            ok, report, error, graph = self.agent.process(
                {'id':'a'*32,'project':'ITAM','repository':'attacker/repo','branch':'main',
                 'expected_sha':'a'*40,'kind':'verify'},
                {'projects':{'ITAM':{'repository':'gyangho/ITAM','path':'C:/repo'}}})
            self.assertFalse(ok)
            self.assertIn('allowlist mismatch', error)


if __name__ == '__main__':
    unittest.main()
