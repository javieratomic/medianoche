#!/usr/bin/env python3
"""Offline, user-local MEDIANOCHE installation. No save/profile migration."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import stat
import struct
import sys
import uuid
import zlib

sys.path.insert(0, str(Path(__file__).absolute().parent / "vendor"))
import vdf

NAME = "MEDIANOCHE"
STEAM64_BASE = 76561197960265728
ARTWORK = ("library_hero.png", "library_logo.png", "library_capsule.png",
           "library_portrait.png", "icon.png")
MARKER = ".medianoche-install.json"


class InstallError(Exception):
    pass


class SafeDir:
    """Pin Linux directories and use no-follow, descriptor-relative operations.

    The Windows branch exists for offline fixture testing only; main requires Linux.
    Linux never writes via an absolute path after opening the directory.
    """
    def __init__(self, path, create=False):
        self.path = Path(os.path.abspath(path))
        self.fd = None
        if os.name == "posix":
            fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
            try:
                for component in self.path.parts[1:]:
                    if create:
                        try:
                            os.mkdir(component, 0o700, dir_fd=fd)
                        except FileExistsError:
                            pass
                    child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    os.close(fd)
                    fd = child
                self.fd = fd
            except BaseException:
                os.close(fd)
                raise
        else:
            current = Path(self.path.anchor)
            for component in self.path.parts[1:]:
                current /= component
                if create:
                    current.mkdir(exist_ok=True)
                if current.is_symlink() or not current.is_dir():
                    raise InstallError(f"Directorio inseguro: {current}")
        self.identity = self._identity()

    def _identity(self):
        info = os.fstat(self.fd) if self.fd is not None else self.path.stat()
        return info.st_dev, info.st_ino

    def check(self):
        if self.fd is not None:
            with SafeDir(self.path) as fresh:
                if fresh.identity != self.identity:
                    raise InstallError(f"La ruta ha cambiado durante la instalacion: {self.path}")
        elif self.path.is_symlink() or self._identity() != self.identity:
            raise InstallError(f"La ruta ha cambiado: {self.path}")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self.fd is not None:
            os.close(self.fd)

    def _args(self, name):
        if not name or name in (".", "..") or "/" in name or "\\" in name:
            raise InstallError("Nombre de archivo inseguro")
        return (name, {"dir_fd": self.fd}) if self.fd is not None else (self.path / name, {})

    def read(self, name):
        target, kwargs = self._args(name)
        self.check()
        if self.fd is None and Path(target).is_symlink():
            raise InstallError(f"Enlace simbolico no permitido: {target}")
        try:
            fd = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_NONBLOCK", 0), **kwargs)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise InstallError(f"Archivo no regular o enlazado: {self.path / name}")
            return stream.read()

    def replace(self, name, data, mode=0o644):
        self.check()
        self.read(name)  # refuse existing symlinks/hardlinks, even though rename would replace them
        temporary = ".medianoche-tmp-" + uuid.uuid4().hex
        target, kwargs = self._args(temporary)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     getattr(os, "O_NOFOLLOW", 0), mode, **kwargs)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
                if self.fd is not None:
                    os.fchmod(stream.fileno(), mode)
            self.check()
            destination, _ = self._args(name)
            if self.fd is not None:
                os.replace(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
                os.fsync(self.fd)
            else:
                os.replace(target, destination)
        finally:
            try:
                os.unlink(target, **kwargs)
            except FileNotFoundError:
                pass

    def remove_created(self, name, expected):
        if self.read(name) != expected:
            raise InstallError(f"No se restaura un archivo modificado externamente: {name}")
        target, kwargs = self._args(name)
        os.unlink(target, **kwargs)
        if self.fd is not None:
            os.fsync(self.fd)


@contextmanager
def installer_lock(home):
    with SafeDir(home) as directory:
        name = ".medianoche-installer.lock"
        directory.check()
        target, kwargs = directory._args(name)
        if directory.fd is None and Path(target).is_symlink():
            raise InstallError("Archivo de bloqueo inseguro")
        fd = os.open(target, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600, **kwargs)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_nlink != 1:
                raise InstallError("Archivo de bloqueo inseguro")
            try:
                if os.name == "posix":
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:
                    import msvcrt
                    if os.fstat(fd).st_size == 0:
                        os.write(fd, b"0")
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise InstallError("Ya hay otra instalacion de MEDIANOCHE en curso") from exc
            directory.check()
            current = os.stat(target, follow_symlinks=False, **kwargs)
            pinned = os.fstat(fd)
            if (current.st_dev, current.st_ino) != (pinned.st_dev, pinned.st_ino):
                raise InstallError("El archivo de bloqueo ha cambiado")
            yield
        finally:
            os.close(fd)  # Keep the lock inode; unlinking it would allow split locks.


def assert_steam_closed(proc_root=Path("/proc")):
    message = "Cierra Steam por completo (Steam > Salir), tambien steamwebhelper, y vuelve a instalar. No se cerrara por la fuerza."
    try:
        processes = list(Path(proc_root).iterdir())
    except OSError as exc:
        raise InstallError("No se puede comprobar si Steam esta cerrado") from exc
    for process in processes:
        if not process.name.isdigit():
            continue
        try:
            comm = (process / "comm").read_text().strip().lower()
            command = (process / "cmdline").read_bytes().split(b"\0")[0].decode("utf-8", "replace")
        except FileNotFoundError:
            continue  # process exited between listing and reading
        except PermissionError as exc:
            raise InstallError("No se pueden inspeccionar todos los procesos; no es seguro modificar Steam") from exc
        executable = Path(command).name.lower()
        if comm in {"steam", "steam.sh", "steamwebhelper", "steamservice", "steam-runtime-l"} or executable in {
                "steam", "steam.sh", "steamwebhelper", "steamservice", "steam-runtime-launcher-service"}:
            raise InstallError(message)


def discover_steam(home, explicit=None):
    home = Path(home).absolute()
    candidates = [Path(explicit)] if explicit else [
        home / ".local/share/Steam", home / ".steam/steam", home / ".steam/root",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
        home / ".var/app/com.valvesoftware.Steam/.steam/steam"]
    found = []
    for candidate in candidates:
        if candidate.exists():
            # Steam's standard .steam/steam alias is normally a symlink. Resolve
            # only this discovery boundary, require it to stay inside HOME, pin below.
            resolved = candidate.resolve(strict=True)
            if not resolved.is_relative_to(home.resolve()):
                raise InstallError("La carpeta de Steam debe estar dentro de HOME")
            with SafeDir(resolved / "config") as directory:
                if directory.read("loginusers.vdf") is None:
                    continue
            if resolved not in found:
                found.append(resolved)
    if len(found) != 1:
        raise InstallError("No se encuentra una unica instalacion de Steam. Inicia sesion una vez, sal de Steam o indica --steam-root.")
    return found[0]


def choose_account(steam, account=None, interactive=False):
    with SafeDir(steam / "config") as directory:
        raw = directory.read("loginusers.vdf")
    try:
        users = vdf.loads(raw.decode("utf-8-sig"), mapper=vdf.VDFDict)["users"]
        choices = []
        for steam64, details in users.items():
            aid = int(steam64) - STEAM64_BASE
            if not 0 < aid < 2**32:
                raise ValueError("steam64 invalido")
            choices.append((str(aid), details.get("AccountName", steam64), details.get("MostRecent") == "1"))
    except (ValueError, TypeError, KeyError, AttributeError, SyntaxError) as exc:
        raise InstallError("loginusers.vdf no es valido; no se ha modificado Steam") from exc
    if account is not None:
        matching = [choice for choice in choices if choice[0] == str(account)]
    else:
        matching = [choice for choice in choices if choice[2]]
        if not matching and len(choices) == 1:
            matching = choices
    if len(matching) == 1:
        return matching[0][0]
    options = ", ".join(f"{aid} ({label})" for aid, label, _ in choices)
    if interactive and choices and account is None:
        print("Elige una cuenta de Steam: " + options)
        selected = input("AccountID: ").strip()
        return choose_account(steam, selected, False)
    raise InstallError("Selecciona una cuenta con --account ACCOUNTID. Cuentas: " + options)


def shortcut_plan(raw, destination):
    try:
        document = vdf.binary_loads(raw, mapper=vdf.VDFDict) if raw is not None else {"shortcuts": {}}
        entries = document["shortcuts"]
        if not isinstance(entries, dict) or any(not key.isdigit() or not isinstance(value, dict)
                                                for key, value in entries.items()):
            raise ValueError("shortcuts invalido")
        # Duplicate keys cannot be safely rewritten; fail instead of silently dropping any.
        def duplicates(value):
            return isinstance(value, dict) and (
                (isinstance(value, vdf.VDFDict) and value.has_duplicates()) or
                any(duplicates(child) for child in value.values()))
        if duplicates(document):
            raise ValueError("claves duplicadas")
        # Convert only after duplicate detection; normal dict assignment replaces values.
        def plain(value):
            return {key: plain(child) for key, child in value.items()} if isinstance(value, dict) else value
        document = plain(document)
        entries = document["shortcuts"]
        exe = '"' + str(destination / "launch.sh") + '"'
        matches = [(key, entry) for key, entry in entries.items()
                   if entry.get("appname", "").casefold() == NAME.casefold() or entry.get("exe") == exe]
        if len(matches) > 1:
            raise ValueError("Hay varios accesos MEDIANOCHE; revisalos en Steam")
        if matches:
            key, entry = matches[0]
            appid = int(entry["appid"]) & 0xffffffff
        else:
            key = str(max((int(key) for key in entries), default=-1) + 1)
            appid = zlib.crc32((exe + NAME).encode("utf-8")) | 0x80000000
            entry = {"IsHidden": 0, "AllowDesktopConfig": 1, "AllowOverlay": 1,
                     "OpenVR": 0, "Devkit": 0, "DevkitGameID": "", "LastPlayTime": 0, "tags": {}}
        if any(other != key and (int(value.get("appid", 0)) & 0xffffffff) == appid
               for other, value in entries.items()):
            raise ValueError("Colision de AppID; no es seguro asignar ilustraciones")
        entry.update(appid=appid if appid < 2**31 else appid - 2**32,
                     appname=NAME, exe=exe, StartDir='"' + str(destination) + '"',
                     LaunchOptions="", icon=str(destination / "artwork/icon.png"))
        entries[key] = entry
        result = vdf.binary_dumps(document)
        vdf.binary_loads(result)  # serialize and validate before the first mutation
        return appid, result
    except (ValueError, TypeError, KeyError, AttributeError, SyntaxError, OverflowError, OSError, struct.error) as exc:
        raise InstallError("shortcuts.vdf no es seguro o es ambiguo; se conserva intacto: " + str(exc)) from exc


def bundle_files(bundle):
    files = {}
    # walk does not follow symlink directories; still explicitly reject every entry.
    for directory, dirs, names in os.walk(bundle, followlinks=False):
        for name in dirs + names:
            path = Path(directory) / name
            if path.is_symlink():
                raise InstallError(f"El paquete contiene un enlace simbolico: {path}")
        for name in names:
            path = Path(directory) / name
            with SafeDir(path.parent) as parent:
                data = parent.read(name)
            if data is None:
                raise InstallError(f"El paquete ha cambiado: {path}")
            files[path.relative_to(bundle)] = data
    required = [Path("launch.sh"), Path("game.love")] + [Path("artwork") / name for name in ARTWORK]
    if any(not files.get(path) for path in required) or not any(
            path.name.endswith(".AppImage") and data for path, data in files.items()):
        raise InstallError("Paquete incompleto: faltan launch.sh, game.love, AppImage o ilustraciones")
    if any(not files[Path("artwork") / name].startswith(b"\x89PNG\r\n\x1a\n") for name in ARTWORK):
        raise InstallError("Las ilustraciones deben ser PNG validos")
    return files


def apply_transaction(changes, expected=None):
    """Back up all old bytes first; never remove anything not created by us."""
    transaction = uuid.uuid4().hex
    prepared = []
    applied = []
    try:
        for path, data, mode, only_missing in changes:
            directory = SafeDir(path.parent, create=True)
            try:
                old = directory.read(path.name)
            except BaseException:
                directory.__exit__()
                raise
            prepared.append((directory, path.name, data, mode, old, only_missing))
            if expected and path in expected and prepared[-1][4] != expected[path]:
                raise InstallError("La configuracion de Steam ha cambiado; no se sobrescribe")
        effective = [item for item in prepared if item[4] != item[2] and not (item[5] and item[4] is not None)]
        for directory, name, data, mode, old, _ in effective:
            assert_steam_closed()
            if old is not None:
                directory.replace(name + ".medianoche-backup-" + transaction, old, 0o600)
        for directory, name, data, mode, old, _ in effective:
            assert_steam_closed()
            if directory.read(name) != old:
                raise InstallError("Un archivo ha cambiado durante la instalacion; vuelve a intentarlo")
            # Record before replace: fsync can fail after the atomic rename succeeded.
            applied.append((directory, name, data, mode, old))
            directory.replace(name, data, mode)
        assert_steam_closed()
    except Exception as exc:
        failures = []
        for directory, name, data, mode, old in reversed(applied):
            try:
                current = directory.read(name)
                if current == old:
                    continue
                if current != data:
                    raise InstallError("cambio externo")
                if old is None:
                    directory.remove_created(name, data)
                else:
                    directory.replace(name, old, mode)
            except Exception:
                failures.append(str(directory.path / name))
        suffix = " Revisa las copias de seguridad: " + ", ".join(failures) if failures else " Se han restaurado los archivos anteriores."
        raise InstallError(str(exc) + suffix) from exc
    finally:
        for directory, *_ in prepared:
            directory.__exit__()


def install(bundle, home=None, install_dir=None, steam_root=None, account=None, interactive=False):
    try:
        return _install(bundle, home, install_dir, steam_root, account, interactive)
    except OSError as exc:
        raise InstallError("No se puede acceder de forma segura a los archivos: " + str(exc)) from exc


def _install(bundle, home, install_dir, steam_root, account, interactive):
    home = Path(home or Path.home()).absolute()
    bundle = Path(os.path.abspath(bundle))
    destination = Path(os.path.abspath(Path(install_dir).expanduser() if install_dir else home / "Games" / NAME))
    if any(character in str(destination) for character in ('"', "\n", "\r", "\0")):
        raise InstallError("La ruta de instalacion contiene caracteres no seguros")
    if not destination.is_relative_to(home) or destination == home:
        raise InstallError("La instalacion debe estar en una subcarpeta de HOME")
    if destination.is_relative_to(bundle) or bundle.is_relative_to(destination):
        raise InstallError("Extrae el paquete fuera del destino de instalacion")
    assert_steam_closed()
    files = bundle_files(bundle)
    steam = discover_steam(home, steam_root)
    if destination.is_relative_to(steam) or steam.is_relative_to(destination):
        raise InstallError("El destino no puede solaparse con Steam")
    with installer_lock(home):
        assert_steam_closed()
        aid = choose_account(steam, account, interactive)
        config = steam / "userdata" / aid / "config"
        if not config.is_dir():
            raise InstallError("La cuenta seleccionada no tiene configuracion local. Abre Steam con esa cuenta y sal.")
        with SafeDir(config) as directory:
            original = directory.read("shortcuts.vdf")
        appid, shortcuts = shortcut_plan(original, destination)
        if destination.exists():
            with SafeDir(destination) as directory:
                marker = directory.read(MARKER)
                if marker is None:
                    raise InstallError("El destino ya existe y no es una instalacion administrada de MEDIANOCHE")
                try:
                    if json.loads(marker).get("game") != NAME:
                        raise ValueError()
                except (ValueError, AttributeError) as exc:
                    raise InstallError("La marca de instalacion no es valida") from exc
        changes = []
        for relative, data in sorted(files.items()):
            mode = 0o755 if relative.name.endswith((".sh", ".AppImage", ".desktop")) else 0o644
            changes.append((destination / relative, data, mode, False))
        changes.append((destination / MARKER, json.dumps({"game": NAME, "version": 1}).encode(), 0o644, False))
        grid = config / "grid"
        mapping = {"library_hero.png": f"{appid}_hero.png", "library_logo.png": f"{appid}_logo.png",
                   "library_capsule.png": f"{appid}.png", "library_portrait.png": f"{appid}p.png",
                   "icon.png": f"{appid}_icon.png"}
        for source, target in mapping.items():
            changes.append((grid / target, files[Path("artwork") / source], 0o644, False))
        # Commit the shortcut last, after the full launch payload and artwork exist.
        changes.append((config / "shortcuts.vdf", shortcuts, 0o600, False))
        apply_transaction(changes, expected={config / "shortcuts.vdf": original})
    print(f"MEDIANOCHE instalado en {destination}. Cuenta: {aid}. Abre Steam y vuelve al Modo Juego.")
    return appid


def main(argv=None):
    parser = argparse.ArgumentParser(description="Instala MEDIANOCHE y sus ilustraciones en una cuenta de Steam (Steam debe estar cerrado).")
    parser.add_argument("--bundle-dir", type=Path, default=Path(__file__).absolute().parent)
    parser.add_argument("--install-dir", type=Path)
    parser.add_argument("--steam-root", type=Path)
    parser.add_argument("--account", help="AccountID numerico de userdata, no SteamID64")
    args = parser.parse_args(argv)
    try:
        if not sys.platform.startswith("linux"):
            raise InstallError("Este instalador requiere SteamOS/Linux con python3")
        install(args.bundle_dir, install_dir=args.install_dir, steam_root=args.steam_root,
                account=args.account, interactive=sys.stdin.isatty())
    except (InstallError, OSError, EOFError) as exc:
        print("No se pudo instalar MEDIANOCHE: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
