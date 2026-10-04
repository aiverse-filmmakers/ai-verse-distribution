import sys
import unittest

from aiverse_distribution.process import CommandResult, ProcessError, run


class ProcessTests(unittest.TestCase):
    def test_argv_is_literal_not_shell_interpolated(self):
        marker = "hello;echo-not-a-shell"
        result = run([sys.executable, "-c", "import sys; print(sys.argv[1])", marker])
        self.assertEqual(result.stdout.strip(), marker)

    def test_structured_stdin_is_passed_without_shell(self):
        payload = '{"protocol":"test/1.0","ok":true}'
        result = run(
            [sys.executable, "-c", "import sys; print(sys.stdin.read())"],
            input_text=payload,
        )
        self.assertEqual(result.stdout.strip(), payload)

    def test_process_failure_sanitizes_message_and_serialized_fields(self):
        code = (
            "import json,sys; "
            "print(json.dumps({'access_token':'stdout-secret'})); "
            "print('Authorization: Bearer stderr-secret', file=sys.stderr); "
            "sys.exit(7)"
        )
        with self.assertRaises(ProcessError) as caught:
            run([sys.executable, "-c", code, "--api-key", "argv-secret", "--password=password-secret"])

        error = caught.exception
        rendered = str(error)
        for secret in ("stdout-secret", "stderr-secret", "argv-secret", "password-secret"):
            self.assertNotIn(secret, rendered)
            self.assertNotIn(secret, error.stdout)
            self.assertNotIn(secret, error.stderr)
            self.assertNotIn(secret, " ".join(error.argv))
        self.assertIn("<redacted>", rendered)

    def test_command_result_dict_is_a_safe_serialization_boundary(self):
        result = CommandResult(
            ["provider", "--token", "argv-secret"],
            1,
            '{"password":"stdout-secret"}',
            "Bearer stderr-secret",
        )
        serialized = str(result.as_dict())
        for secret in ("stdout-secret", "stderr-secret", "argv-secret"):
            self.assertNotIn(secret, serialized)
        self.assertIn("<redacted>", serialized)


if __name__ == "__main__":
    unittest.main()
