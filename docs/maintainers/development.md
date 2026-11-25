# Local development on Windows

## CI-equivalent environment

Install Git and Python **3.14.1 x64**. Use the repository root and an isolated Python environment.

~~~powershell
py -3.14 -m venv .venv
$python = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $python --version
& $python -m pip install -r requirements-dev.txt
& $python tools/native_assets.py check
& $python -m unittest discover -s tests
& $python tools/package_mod.py
~~~

Lupa runs the Lua 5.4 tests. Pillow and cityhash are used by the asset build and its tests. Node 24 and the locked npm dependencies are used for release version planning. The CI-equivalent checks use the Unreal binaries committed to the repository.

## Blender and Unreal tools

| Tool | Verified build | Setup |
| --- | --- | --- |
| Blender | **5.2.3 LTS**, Windows x64, commit **e13b728c6880** | Install Blender 5.2.3 or extract the portable package. Point `--blender` at `blender.exe`. [Blender releases](https://download.blender.org/release/Blender5.2/) |
| retoc | Voyage UE 5.8 **v0.1.5-rc3**, source `49b7721` | Extract the release into a tools directory. Keep its companion files beside `retoc.exe`. [Voyage retoc release](https://github.com/ihsoft/retoc/releases/tag/v0.1.5-rc3) |
| repak | **0.2.3**, Windows MSVC x64 | Extract `repak.exe`. [repak release](https://github.com/trumank/repak/releases/tag/v0.2.3) |
| UAssetGUI | Voyage UE 5.8 **v1.1.1-rc3**, GUI `df18b5f` and UAssetAPI `21c982f` | Extract the release, including its `Data` folder. [Voyage UAssetGUI release](https://github.com/ihsoft/UAssetGUI/releases/tag/v1.1.1-rc3) |
| jmap_dumper | Voyage **v0.2.0-rc3**, source `fad7b92` | Extract `jmap_dumper.exe`. [Voyage JMAP release](https://github.com/ihsoft/jmap/releases/tag/v0.2.0-rc3) |
| UE4SS | **3.0.1 Beta**, Git SHA **527a483b** | Install the build compatible with the game under `Voyage/Binaries/Win64`. Generate a JMAP on the exact build you are targeting. [UE4SS dumper documentation](https://docs.ue4ss.com/feature-overview/dumpers.html#jmap-dumper) |

Blender uses its own Python and `bpy`. Use `.venv` separately for the repository scripts. No Blender add-on is needed for the two masters. The wrapper opens each file in Blender background mode with factory settings and starts the exporter using Blender's Python. It writes the mesh exports and contours into a scratch tree. The repository Python then bakes the atlas and runs the Unreal resource builder. [Blender command-line manual](https://docs.blender.org/manual/en/5.2/advanced/command_line/arguments.html)

To run a geometry export while editing a model, open the master in Blender background mode. This writes the model's two .snm files under Scripts/shipnet. Use the full rebuild workflow below to update the atlas, Unreal packages and manifest before committing.

~~~powershell
& $blender --background --factory-startup --disable-autoexec .\3d_models\rail-controller-v05.blend `
    --python-exit-code 1 --python .\tools\export_rail_model.py
~~~

## Rebuild the assets

1. Find the installed Steam game root using **Properties → Installed Files → Browse**. It is the directory under `steamapps/common` containing `Voyage/Content/Paks`.
2. Install a development ZIP in that game or a Steam-layout test copy. Launch with the mod enabled. It writes the full game version, project version and Steam BuildID to `ShipNetAutomation/Logs/game-version.json` under the UE4SS mods directory. Use that report with the same game build.
3. On the same build, generate a `.jmap` using UE4SS's **JMAP Dumper** with Blueprint-generated types included. Close the game before rebuilding. Keep the dump out of Git.
4. Set the example paths below to your own installation and tool directories. A ZIP containing the committed assets is enough to bootstrap the diagnostic report.

~~~powershell
$game = 'D:\SteamLibrary\steamapps\common\Voyage'
$tools = 'D:\Tools\Voyage'
$blender = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
$jmap = Join-Path $game 'Voyage\Binaries\Win64\ue4ss\Voyage-5.8.2-0+UE5-527a483b.jmap'

& $python tools/game_build.py --game-root $game

$rebuild = @(
    '--game-root', $game,
    '--blender', $blender,
    '--retoc', (Join-Path $tools 'retoc\retoc.exe'),
    '--repak', (Join-Path $tools 'repak\repak.exe'),
    '--uassetgui', (Join-Path $tools 'UAssetGUI\UAssetGUI.exe'),
    '--jmap-dumper', (Join-Path $tools 'jmap\jmap_dumper.exe'),
    '--jmap', $jmap
)
& $python tools/native_assets.py rebuild @rebuild
& $python tools/native_assets.py check
& $python -m unittest discover -s tests
& $python tools/package_mod.py
~~~

Supply `--version-report` if the matching capture is stored outside the installation. Supply `--force-native` to regenerate the full Unreal package set even when the current inputs and products match. The [asset pipeline](asset-pipeline.md) describes what the wrapper records and which changes require a rebuild.

## Diagnose local failures

- **Blender fails to open a master**. Check `& $blender --version` and compare it with the pinned build above. Pass the path to the executable and keep the quotation around paths with spaces.
- **The report is missing or reports another BuildID**. Launch the mod on the target Steam installation to capture a new report. Check the UE4SS log for the line containing **Game version**.
- **Unreal serialization fails**. Verify that retoc, UAssetGUI and jmap_dumper are the Voyage builds above. Confirm the JMAP was generated after the last game update.
- **SHA-256 differs in CI**. Check the path named by the verifier. Rerun the local rebuild for asset inputs or restore a missing package from the intended commit.
