import json
import unittest

from aiverse_distribution.redaction import sanitize, sanitize_text


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

    def test_json_encoded_error_text_is_redacted_recursively(self):
        text = '{"message":"child failed","details":{"access_token":"json-secret"}}'
        sanitized = sanitize_text(text)
        self.assertNotIn("json-secret", sanitized)
        self.assertIn("<redacted>", sanitized)
        self.assertEqual(
            sanitize(json.loads(sanitized))["details"]["access_token"],
            "<redacted>",
        )


if __name__ == "__main__":
    unittest.main()
