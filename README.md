# Ship Net Automation

![Ship Net Automation for The Last Caretaker](artwork/branding/github/readme-banner.png)

**[<img src="artwork/branding/github/nexus-mods-icon.png" width="20" height="20" alt=""> View on Nexus Mods](https://www.nexusmods.com/thelastcaretaker/mods/454)**

Ship Net Automation adds two buildable winch controllers to *The Last Caretaker*. Both attach to the stock fishing winch and use the ship's electrical network.

## Winch controllers

| Winch Automator Basic | Winch Automator Advanced |
| :---: | :---: |
| <a href="artwork/models/basic-winch-automator-v01.png"><img src="artwork/models/basic-winch-automator-v01.png" height="150" alt="Standalone 3D render of the Basic controller"></a> | <a href="artwork/models/rail-controller-v05.png"><img src="artwork/models/rail-controller-v05.png" height="150" alt="Standalone 3D render of the Advanced controller"></a> |
| **Engineering level 6 · 1 point**<br>Raises the net and flashes an amber lamp. Empty the stock drawer to resume fishing. | **Engineering level 10 · 2 points**<br>Moves catch into a 50 kg cabinet, then lowers the net when the drawer is empty. |
| <img src="artwork/branding/github/basic-installed.jpg" width="380" alt="Basic controller mounted across the front of the blue fishing winch"> | <img src="artwork/branding/github/advanced-installed.jpg" width="380" alt="Advanced cabinet mounted next to the blue fishing winch"> |

Build the researched controller on the winch, connect **POWER IN**, then interact with the onboard display to switch automation on or off. The display shows catch weight, net capacity and electrical draw.

## Installation

Install with Vortex from [Nexus Mods](https://www.nexusmods.com/thelastcaretaker/mods/454?tab=files) or download the ZIP from [GitHub Releases](https://github.com/umanamente/tlc-ship-net-automation-mod/releases). See the [installation instructions](docs/gamers/installation.md) for the UE4SS requirement and manual steps. The [player guide](docs/gamers/guide.md) covers research and operation, and the [troubleshooting guide](docs/gamers/troubleshooting.md) covers common issues. Each release lists the game version and Steam BuildID used to build and test it. The same compatibility record is included in the ZIP and the [changelog](CHANGELOG.md).

For contributions, see [local development setup](docs/maintainers/development.md), the [asset pipeline](docs/maintainers/asset-pipeline.md) and [architecture decisions](docs/maintainers/adr/README.md). AI agents start with [AGENTS.md](AGENTS.md).
