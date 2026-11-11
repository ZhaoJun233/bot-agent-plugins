"""Actual GitHub combined/detailed status response shapes; synthetic identities only."""
import copy
import json
import unittest
from marketplace_gate import verify_premerge

BASE = 'a' * 40
HEAD = 'b' * 40

class StatusEndpointApi:
    repository = 'example/market'

    def __init__(self):
        self.paths = []
        self.pull = {'state': 'open', 'base': {'sha': BASE, 'ref': 'main', 'repo': {
            'full_name': self.repository, 'default_branch': 'main'}},
            'head': {'sha': HEAD, 'repo': {'full_name': 'author/market'}}}
        self.status = {'context': 'marketplace-gate', 'state': 'success',
                       'creator': {'login': 'github-actions[bot]'},
                       'description': 'Approved PR 17 base ' + BASE}
        self.statuses = [self.status]

    def get(self, path):
        self.paths.append(path)
        if path == '/pulls/17':
            return copy.deepcopy(self.pull)
        if path == '/commits/' + HEAD + '/status':
            return {'state': 'success', 'statuses': [{k: v for k, v in self.status.items() if k != 'creator'}]}
        if path == '/commits/' + HEAD + '/statuses':
            return copy.deepcopy(self.statuses)
        raise AssertionError('Unexpected endpoint: ' + path)

    def file(self, path, revision):
        return json.dumps({'schemaVersion': 1, 'generatedAt': '2026-01-01T00:00:00Z', 'entries': []}).encode()

class GitHubStatusContractTests(unittest.TestCase):
    def test_actual_detailed_status_response_passes(self):
        api = StatusEndpointApi()
        self.assertEqual(HEAD, verify_premerge(api, 17, BASE, HEAD)['head']['sha'])
        self.assertIn('/commits/' + HEAD + '/statuses', api.paths)
        self.assertNotIn('/commits/' + HEAD + '/status', api.paths)

    def test_missing_actor_cannot_borrow_a_combined_success(self):
        api = StatusEndpointApi()
        api.status.pop('creator')
        with self.assertRaisesRegex(ValueError, 'owner gate'):
            verify_premerge(api, 17, BASE, HEAD)

    def test_wrong_actor_is_rejected(self):
        api = StatusEndpointApi()
        api.status['creator']['login'] = 'other-bot'
        with self.assertRaisesRegex(ValueError, 'owner gate'):
            verify_premerge(api, 17, BASE, HEAD)

    def test_latest_failure_cannot_use_an_older_success(self):
        api = StatusEndpointApi()
        approved = copy.deepcopy(api.status)
        api.status['state'] = 'failure'
        api.statuses.append(approved)
        with self.assertRaisesRegex(ValueError, 'owner gate'):
            verify_premerge(api, 17, BASE, HEAD)

    def test_missing_gate_is_rejected(self):
        api = StatusEndpointApi()
        api.statuses = []
        with self.assertRaisesRegex(ValueError, 'owner gate'):
            verify_premerge(api, 17, BASE, HEAD)

    def test_other_base_approval_is_rejected(self):
        api = StatusEndpointApi()
        api.status['description'] = 'Approved PR 17 base ' + 'c' * 40
        with self.assertRaisesRegex(ValueError, 'different PR or base'):
            verify_premerge(api, 17, BASE, HEAD)

    def test_candidate_drift_is_rejected_before_status_read(self):
        api = StatusEndpointApi()
        api.pull['head']['sha'] = 'c' * 40
        with self.assertRaisesRegex(ValueError, 'changed'):
            verify_premerge(api, 17, BASE, HEAD)
        self.assertEqual(['/pulls/17'], api.paths)

if __name__ == '__main__':
    unittest.main()
