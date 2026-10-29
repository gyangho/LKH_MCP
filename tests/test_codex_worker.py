"""Test isolated worker path validation without invoking Codex."""
import unittest

from worker.codex_worker import _safe, _execute


class WorkerTests(unittest.TestCase):
    def test_allows_explicit_source_files(self):
        self.assertTrue(_safe("src/service.py"))
        self.assertTrue(_safe("frontend/App.tsx"))

    def test_rejects_unsafe_paths(self):
        for name in ("../secret.py", "/etc/passwd", "src/../other.py",
                     ".git/config", "src/.env", "src/token.py",
                     "a\\b.py", "src/secret_key.py"):
            with self.subTest(name=name):
                self.assertFalse(_safe(name))

    def test_rejects_feature_mode_before_executing(self):
        with self.assertRaises(ValueError):
            _execute({"mode": "feature_implementation", "symptom": "new feature",
                      "log_excerpt": "", "files": {"src/main.py": "pass"}})

    def test_rejects_unapproved_payload_shape(self):
        with self.assertRaises(ValueError):
            _execute({"mode": "diagnose", "prompt": "arbitrary commands",
                      "symptom": "issue", "files": {"src/main.py": "pass"},
                      "log_excerpt": ""})


if __name__ == "__main__":
    unittest.main()
