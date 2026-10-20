"""Offline installer fixtures; Linux additionally exercises dir_fd/flock guards."""
import importlib.util
import os
import contextlib
import io
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "steam_installer", ROOT / "distribution/steamos/install_steam.py")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)
vdf = installer.vdf


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"
        self.home.mkdir()
        self.bundle = Path(self.temp.name) / "extracted"
        (self.bundle / "artwork").mkdir(parents=True)
        for name in installer.ARTWORK:
            (self.bundle / "artwork" / name).write_bytes(b"\x89PNG\r\n\x1a\nfixture-" + name.encode())
        (self.bundle / "launch.sh").write_bytes(b"#!/bin/sh\nexit 0\n")
        (self.bundle / "game.love").write_bytes(b"game fixture")
        (self.bundle / "love.AppImage").write_bytes(b"runtime fixture")
        self.steam = self.home / ".local/share/Steam"
        (self.steam / "config").mkdir(parents=True)
        self.config = self.steam / "userdata/42/config"
        self.config.mkdir(parents=True)
        self.login({42: "1"})
        self.shortcuts = self.config / "shortcuts.vdf"
        self.other = {"appid": 123, "appname": "Otro juego", "exe": '"/other"',
                      "tags": {"0": "Favoritos"}, "custom": "conservar"}
        self.shortcuts.write_bytes(vdf.binary_dumps({"shortcuts": {"0": self.other}}))
        self.guard = mock.patch.object(installer, "assert_steam_closed")
        self.guard.start()
        self.addCleanup(self.guard.stop)
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def login(self, accounts):
        users = {str(installer.STEAM64_BASE + aid): {"MostRecent": recent,
                 "AccountName": "cuenta" + str(aid)} for aid, recent in accounts.items()}
        (self.steam / "config/loginusers.vdf").write_text(vdf.dumps({"users": users}), encoding="utf-8")

    def run_install(self, **kwargs):
        with mock.patch.dict(os.environ, {"HOME": str(self.home), "USERPROFILE": str(self.home)}):
            return installer.install(self.bundle, home=Path.home(), **kwargs)

    def data(self):
        return vdf.binary_loads(self.shortcuts.read_bytes())["shortcuts"]

    def test_preservation_idempotence_unsigned_art_names_and_backups(self):
        before = self.shortcuts.read_bytes()
        appid = self.run_install()
        data = self.data()
        self.assertEqual(data["0"], self.other)
        self.assertEqual(data["1"]["appid"] & 0xffffffff, appid)
        self.assertGreaterEqual(appid, 0x80000000)
        self.assertLess(data["1"]["appid"], 0)
        expected = {f"{appid}.png", f"{appid}p.png", f"{appid}_hero.png",
                    f"{appid}_logo.png", f"{appid}_icon.png"}
        self.assertEqual({p.name for p in (self.config / "grid").iterdir()}, expected)
        self.assertEqual((self.config / "grid" / f"{appid}p.png").read_bytes(),
                         (self.bundle / "artwork/library_portrait.png").read_bytes())
        self.assertTrue(any(p.read_bytes() == before for p in self.config.glob("shortcuts.vdf.medianoche-backup-*")))
        installed = self.home / "Games/MEDIANOCHE"
        self.assertEqual((installed / "game.love").read_bytes(), b"game fixture")
        unchanged = self.shortcuts.read_bytes()
        self.assertEqual(self.run_install(), appid)
        self.assertEqual(self.shortcuts.read_bytes(), unchanged)
        self.assertEqual(len(self.data()), 2)

    def test_old_managed_hero_is_updated_and_backed_up_unrelated_art_preserved(self):
        appid = self.run_install()
        custom = self.config / "grid" / f"{appid}_hero.png"
        custom.write_bytes(b"my custom hero")
        unrelated = self.config / "grid/123.png"
        unrelated.write_bytes(b"other art")
        self.run_install()
        self.assertEqual(custom.read_bytes(), (self.bundle / "artwork/library_hero.png").read_bytes())
        backups = list(custom.parent.glob(custom.name + ".medianoche-backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b"my custom hero")
        self.assertEqual(unrelated.read_bytes(), b"other art")

    def test_name_match_keeps_appid_and_custom_fields(self):
        self.other.update(appname="MEDIANOCHE", appid=-123)
        self.shortcuts.write_bytes(vdf.binary_dumps({"shortcuts": {"0": self.other}}))
        self.assertEqual(self.run_install(), (-123) & 0xffffffff)
        self.assertEqual(len(self.data()), 1)
        self.assertEqual(self.data()["0"]["custom"], "conservar")

    def test_missing_asset_and_bad_vdf_leave_config_unchanged(self):
        before = self.shortcuts.read_bytes()
        (self.bundle / "artwork/icon.png").unlink()
        with self.assertRaises(installer.InstallError):
            self.run_install()
        self.assertEqual(self.shortcuts.read_bytes(), before)
        (self.bundle / "artwork/icon.png").write_bytes(b"\x89PNG\r\n\x1a\nicon")
        self.shortcuts.write_bytes(b"broken")
        with self.assertRaises(installer.InstallError):
            self.run_install()
        self.assertEqual(self.shortcuts.read_bytes(), b"broken")

    def test_ambiguous_account_requires_choice(self):
        self.login({42: "1", 99: "1"})
        before = self.shortcuts.read_bytes()
        with self.assertRaisesRegex(installer.InstallError, "cuenta"):
            self.run_install()
        self.assertEqual(self.shortcuts.read_bytes(), before)
        self.run_install(account="42")
        self.assertFalse((self.steam / "userdata/99/config/shortcuts.vdf").exists())

    def test_most_recent_not_every_account(self):
        self.login({42: "1", 99: "0"})
        self.run_install()
        self.assertFalse((self.steam / "userdata/99/config/shortcuts.vdf").exists())

    def test_steam_guard_prevents_every_mutation(self):
        before = self.shortcuts.read_bytes()
        with mock.patch.object(installer, "assert_steam_closed", side_effect=installer.InstallError("Cierra Steam")):
            with self.assertRaisesRegex(installer.InstallError, "Cierra Steam"):
                self.run_install()
        self.assertEqual(self.shortcuts.read_bytes(), before)
        self.assertFalse((self.home / "Games").exists())

    def test_commit_failure_rolls_back_config_and_art(self):
        before = self.shortcuts.read_bytes()
        original = installer.SafeDir.replace
        count = 0

        def fail_once(directory, name, data, mode=0o644):
            nonlocal count
            if name.endswith("_logo.png"):
                count += 1
                if count == 1:
                    raise OSError("injected disk failure")
            return original(directory, name, data, mode)

        with mock.patch.object(installer.SafeDir, "replace", fail_once):
            with self.assertRaises(installer.InstallError):
                self.run_install()
        self.assertEqual(self.shortcuts.read_bytes(), before)
        self.assertEqual(list((self.config / "grid").glob("*.png")), [])

    def test_conflicting_duplicate_matches_abort(self):
        self.shortcuts.write_bytes(vdf.binary_dumps({"shortcuts": {
            "0": dict(self.other, appname="MEDIANOCHE"),
            "1": dict(self.other, appname="MEDIANOCHE")}}))
        before = self.shortcuts.read_bytes()
        with self.assertRaises(installer.InstallError):
            self.run_install()
        self.assertEqual(self.shortcuts.read_bytes(), before)

    def test_flatpak_discovery(self):
        target = self.home / ".var/app/com.valvesoftware.Steam/.local/share/Steam"
        target.parent.mkdir(parents=True)
        self.steam.rename(target)
        self.run_install()
        self.assertTrue((target / "userdata/42/config/shortcuts.vdf").exists())

    def test_proc_guard_real_fixtures(self):
        self.guard.stop()
        proc = Path(self.temp.name) / "proc"
        (proc / "123").mkdir(parents=True)
        (proc / "123/comm").write_text("steamwebhelper\n")
        (proc / "123/cmdline").write_bytes(b"/steam/steamwebhelper\x00")
        with self.assertRaisesRegex(installer.InstallError, "Cierra Steam"):
            installer.assert_steam_closed(proc)
        (proc / "123/comm").write_text("python\n")
        (proc / "123/cmdline").write_bytes(b"python\x00test_steam_installer.py\x00")
        installer.assert_steam_closed(proc)

    def test_custom_install_directory_and_renamed_managed_shortcut(self):
        target = self.home / "Games/Mis juegos/MEDIANOCHE"
        appid = self.run_install(install_dir=target)
        data = self.data()
        data["1"]["appname"] = "Mi nombre personalizado"
        self.shortcuts.write_bytes(vdf.binary_dumps({"shortcuts": data}))
        self.assertEqual(self.run_install(install_dir=target), appid)
        self.assertEqual(len(self.data()), 2)
        self.assertEqual(self.data()["1"]["exe"], '"' + str(target / "launch.sh") + '"')

    def test_fresh_shortcuts_file(self):
        self.shortcuts.unlink()
        self.run_install()
        self.assertEqual(len(self.data()), 1)
        self.assertEqual(self.data()["0"]["appname"], "MEDIANOCHE")

    def test_missing_runtime_and_unsafe_destination(self):
        (self.bundle / "love.AppImage").unlink()
        before = self.shortcuts.read_bytes()
        with self.assertRaises(installer.InstallError):
            self.run_install()
        with self.assertRaises(installer.InstallError):
            self.run_install(install_dir=self.home / "../outside")
        self.assertEqual(self.shortcuts.read_bytes(), before)

    def test_unmanaged_destination_is_not_overwritten(self):
        target = self.home / "Games/MEDIANOCHE"
        target.mkdir(parents=True)
        (target / "game.love").write_bytes(b"not ours")
        with self.assertRaises(installer.InstallError):
            self.run_install()
        self.assertEqual((target / "game.love").read_bytes(), b"not ours")

    def test_duplicate_vdf_keys_rejected_without_data_loss(self):
        entries = vdf.VDFDict()
        entries["0"] = self.other
        entries["0"] = dict(self.other, appname="Otro mas")
        raw = vdf.binary_dumps({"shortcuts": entries})
        self.shortcuts.write_bytes(raw)
        with self.assertRaises(installer.InstallError):
            self.run_install()
        self.assertEqual(self.shortcuts.read_bytes(), raw)

    def test_external_change_between_plan_and_commit_is_preserved(self):
        original = installer.shortcut_plan
        external = vdf.binary_dumps({"shortcuts": {"0": dict(self.other, appname="externo")}})

        def changed(raw, destination):
            result = original(raw, destination)
            self.shortcuts.write_bytes(external)
            return result

        with mock.patch.object(installer, "shortcut_plan", changed):
            with self.assertRaisesRegex(installer.InstallError, "ha cambiado"):
                self.run_install()
        self.assertEqual(self.shortcuts.read_bytes(), external)

    def test_final_guard_failure_rolls_back_committed_shortcuts(self):
        before = self.shortcuts.read_bytes()

        def guard():
            if self.shortcuts.read_bytes() != before:
                raise installer.InstallError("Cierra Steam")

        with mock.patch.object(installer, "assert_steam_closed", side_effect=guard):
            with self.assertRaisesRegex(installer.InstallError, "Cierra Steam"):
                self.run_install()
        self.assertEqual(self.shortcuts.read_bytes(), before)

    def test_concurrent_installer_lock(self):
        with installer.installer_lock(self.home):
            with self.assertRaisesRegex(installer.InstallError, "otra instalacion"):
                self.run_install()

    def test_desktop_passes_space_and_metacharacter_paths_as_data(self):
        desktop = ROOT / "distribution/steamos/Install-MEDIANOCHE.desktop"
        command = next(line[5:] for line in desktop.read_text().splitlines() if line.startswith("Exec="))
        arguments = shlex.split(command)
        self.assertEqual(arguments[:2], ["python3", "-c"])
        self.assertEqual(arguments[3:], ["%k"])
        path = "/home/deck/Downloads/Juego con espacios;$(touch nope)/Install-MEDIANOCHE.desktop"
        with mock.patch.object(os, "execv") as execute, mock.patch.object(sys, "argv", ["-c", path]):
            exec(arguments[2], {})
        execute.assert_called_once_with("/bin/sh", ["sh", str(Path(path).parent / "install.sh")])

    @unittest.skipUnless(os.name == "posix", "Linux symlinks/dir_fd")
    def test_directory_replaced_after_open_is_rejected(self):
        target = self.home / "race"
        target.mkdir()
        with installer.SafeDir(target) as directory:
            target.rename(self.home / "old-race")
            target.mkdir()
            with self.assertRaises(installer.InstallError):
                directory.replace("must-not-exist", b"bad")
        self.assertFalse((target / "must-not-exist").exists())

    @unittest.skipUnless(os.name == "posix", "Linux symlinks/dir_fd")
    def test_bundle_symlink_and_hardlinked_config_rejected(self):
        outside = self.home / "outside"
        outside.write_bytes(b"untouched")
        (self.bundle / "link").symlink_to(outside)
        with self.assertRaises(installer.InstallError):
            self.run_install()
        (self.bundle / "link").unlink()
        os.link(self.shortcuts, self.home / "hardlink")
        with self.assertRaises(installer.InstallError):
            self.run_install()
        self.assertEqual(outside.read_bytes(), b"untouched")

    @unittest.skipUnless(os.name == "posix", "Linux symlinks/dir_fd")
    def test_symlink_target_rejected(self):
        outside = self.home / "outside"
        outside.write_bytes(b"untouched")
        self.shortcuts.unlink()
        self.shortcuts.symlink_to(outside)
        with self.assertRaises(installer.InstallError):
            self.run_install()
        self.assertEqual(outside.read_bytes(), b"untouched")


if __name__ == "__main__":
    unittest.main()
