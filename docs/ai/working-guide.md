# AI working guide

## Start from the task

- Lua code and runtime meshes live in **src/ShipNetAutomation/Scripts**. Read the [architecture](../maintainers/architecture.md) before changing device state or game-thread code.
- The source of each model is its Blender file in **3d_models/**. The editable assets and where their outputs go are documented in [the asset pipeline](../maintainers/asset-pipeline.md).
- Recipes, engineering unlocks, native mounting and game package generation live in **tools/construction_*.py** and **tools/build_construction.py**.
- Use [local development setup](../maintainers/development.md) for exact executable versions, paths, JMAP and Blender commands.

## Check changes

~~~powershell
.\.venv\Scripts\python.exe tools/native_assets.py check
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe tools/package_mod.py
~~~

On a hash mismatch, identify the changed path in the error and run the documented local rebuild if it is an asset input. Keep the regenerated files and the manifest in the same commit. Capture the running game identity with UE4SS before targeting a new Steam build.

Report Lua/Python tests, asset generation and in-game validation separately. Use an isolated test profile for unattended game checks. Follow the [release checklist](../maintainers/releases.md) before recording a build as gameplay-tested.
