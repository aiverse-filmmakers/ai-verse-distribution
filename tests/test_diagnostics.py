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

    def test_environment_and_opaque_credentials_are_redacted(self):
        samples = [
            "OPENAI_API_KEY=environment-secret-value",
            "AWS_SECRET_ACCESS_KEY=aws-secret-value",
            "ghp_" + "g" * 32,
            "sk-proj-" + "s" * 32,
            "AIza" + "a" * 35,
            "xoxb-" + "x" * 24,
            "eyJ" + "a" * 18 + "." + "b" * 18 + "." + "c" * 18,
            "https://service-user:url-secret@example.invalid/path",
        ]
        for secret in samples:
            with self.subTest(secret_prefix=secret[:12]):
                sanitized = sanitize_text(secret)
                self.assertNotIn(secret.split("=")[-1], sanitized)
                self.assertNotIn(secret, sanitized)
                self.assertIn("<redacted>", sanitized)


if __name__ == "__main__":
    unittest.main()
