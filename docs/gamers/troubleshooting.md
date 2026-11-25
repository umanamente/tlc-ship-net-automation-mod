# Troubleshooting

- **Recipe missing.** Check the game root and the UE4SS log. The three files with the ShipNetWinch stem belong in **Voyage/Content/Paks**. The catalogue descriptor belongs in **Voyage/Mods/ShipNetAutomationCatalogue**. Research the recipe before opening the Build menu.
- **Red preview.** Check that the preview is aimed at the right area of the winch and that the mount is clear of cables, obstructions and an existing automator.
- **Lightning icon on the whole display.** The receiver has no stored electricity. Attach a live cable and let it recharge. The switch returns when the receiver has charge.
- **Raised drawer stays up.** Empty the Basic drawer. For Advanced, check power, cabinet space and the saved automation setting.
- **Diagnostic information.** Open **F4 → Settings** and enable the Debug tab. The UE4SS log reports the shortcut if F4 is already in use. The mod records the active game identity in **ShipNetAutomation/Logs/game-version.json**.
