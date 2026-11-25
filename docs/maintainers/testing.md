# Testing

From the local Python environment, run the asset check, `python -m unittest discover -s tests` and the package build. Tests execute Lua against mocked UE4SS objects and inspect the committed Unreal registry and exported meshes.

For release acceptance, install the candidate ZIP in a separate save or test profile. Check both Engineering unlocks, mount validation, power connection, the display switch, automatic haul and manual haul. For Basic, remove some catch and confirm it waits until the drawer is empty. For Advanced, check partial transfer and resumption after making room, then reload and verify the inventory and switch. Check recovery after power returns. Record the mod version, Steam BuildID, project version, UE4SS build and what was exercised.

Review `Logs/game-version.json` for the game identity actually loaded. Startup and asset checks provide separate evidence from the gameplay checks above.
