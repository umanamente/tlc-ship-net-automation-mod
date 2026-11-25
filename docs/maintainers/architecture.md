# Architecture

**Scripts/main.lua** schedules the observers and automators on the game thread. Discovery finds the stock winch and catches on the local ship. The automation modules decide when to haul, transfer cargo or lower the net given the live drawer, power and inventory signals.

Both mount recipes and their engineering unlocks are authored as Unreal resources. Lua binds to the constructed module, drives the display and reacts to the saved automation switch. Basic uses the stock drawer for catch. Advanced moves catch into its own cabinet. Preserve item data and stock drawer contents when a transfer is partial.

The installed-build check reads the Steam manifest beside the game. The version reader queries the Voyage Blueprint library and the active release metadata on the game thread. The small JSON report contains release identity fields and a UTC capture time.
