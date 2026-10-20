"""Check the Windows release without requiring a GPU on hosted CI runners."""
import io
from pathlib import Path
import sys
import zipfile

package = Path(sys.argv[1])
with zipfile.ZipFile(package) as archive:
    names = archive.namelist()
    executable = next(n for n in names if n.endswith('/MEDIANOCHE.exe'))
    prefix = executable.removesuffix('MEDIANOCHE.exe')
    for required in ('love.dll', 'lua51.dll', 'SDL2.dll', 'OpenAL32.dll', 'LICENSE.txt',
                     'licenses/LOVE-license.txt', 'licenses/LibreBaskerville-OFL.txt'):
        assert prefix + required in names, required
    fused = archive.read(executable)
    assert fused.startswith(b'MZ'), 'expected PE executable'
    with zipfile.ZipFile(io.BytesIO(fused)) as game:
        assert 'main.lua' in game.namelist() and 'conf.lua' in game.namelist()
        chunks = 0
        for name in game.namelist():
            assert not name.startswith('assets/_src/'), name
            assert name.endswith(('.lua', '.png', '.ttf', '.otf', '/OFL.txt')), name
            if name.endswith('.lua'):
                data = game.read(name)
                assert data.startswith(b'\x1bLJ') and data[4] & 2, name
                chunks += 1
        assert chunks > 0
        print('OK Windows PE + DLLs + licenses;', chunks, 'stripped LuaJIT chunks')
