import unittest

from aiverse_distribution.redaction import sanitize


class DiagnosticsTests(unittest.TestCase):
    def test_sensitive_keys_are_removed(self):
        payload = {
            "token": "abc123",
            "nested": {"password": "hunter2"},
        }
        sanitized = sanitize(payload)
        self.assertEqual(sanitized["token"], "<redacted>")
        self.assertEqual(sanitized["nested"]["password"], "<redacted>")

    def test_sensitive_text_is_redacted(self):
        payload = {
            "stdout": "Authorization: Bearer abc.def.ghi\napi_key=super-secret-value",
            "stderr": "refresh_token: another-value",
        }
        rendered = str(sanitize(payload))
        self.assertNotIn("abc.def.ghi", rendered)
        self.assertNotIn("super-secret-value", rendered)
        self.assertNotIn("another-value", rendered)
        self.assertIn("<redacted>", rendered)


if __name__ == "__main__":
    unittest.main()
