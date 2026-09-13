import sys
import unittest

from aiverse_distribution.process import run


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


if __name__ == "__main__":
    unittest.main()
