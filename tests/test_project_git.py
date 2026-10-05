import unittest
from unittest.mock import patch

from aiverse_distribution.project_git import git_install_plan
from aiverse_distribution.release_catalog import DistributionError


class GitInstallPlanTests(unittest.TestCase):
    def test_mac_reuses_existing_homebrew(self):
        with patch("platform.system", return_value="Darwin"), patch("shutil.which", side_effect=lambda name: "/tools/brew" if name == "brew" else None):
            plan = git_install_plan()
        self.assertEqual(plan["commands"], [["/tools/brew", "install", "git"]])

    def test_mac_without_brew_uses_apple_installer(self):
        with patch("platform.system", return_value="Darwin"), patch("shutil.which", side_effect=lambda name: "/usr/bin/xcode-select" if name == "xcode-select" else None):
            plan = git_install_plan()
        self.assertTrue(plan["async"])
        self.assertEqual(plan["commands"], [["/usr/bin/xcode-select", "--install"]])

    def test_linux_admin_password_cannot_block_in_background(self):
        with patch("platform.system", return_value="Linux"), patch("os.geteuid", return_value=1000, create=True), patch("shutil.which", side_effect=lambda name: "/usr/bin/" + name if name in ("apt-get", "sudo") else None):
            plan = git_install_plan()
        self.assertEqual(plan["commands"][0], ["/usr/bin/sudo", "-n", "/usr/bin/apt-get", "update"])
        self.assertEqual(plan["commands"][1][-3:], ["install", "--yes", "git"])

    def test_windows_exact_user_scoped_git_package(self):
        with patch("platform.system", return_value="Windows"), patch("shutil.which", return_value="winget.exe"):
            plan = git_install_plan()
        self.assertIn("Git.Git", plan["commands"][0])
        self.assertIn("--exact", plan["commands"][0])
        self.assertEqual(plan["commands"][0][plan["commands"][0].index("--scope") + 1], "user")

    def test_unsupported_package_manager_stops(self):
        with patch("platform.system", return_value="unknown"), self.assertRaises(DistributionError):
            git_install_plan()
