# 0008 · A persistent localized LCD becomes interactive in close view

**Status** — Accepted. Shipped in v0.1.0.

## Context

The stock device screens stay readable in the world while the player walks away. A modal-only control would hide the automator's status whenever the player leaves it. Earlier interactions could open both Settings and the cabinet on one press, and a prototype screen plane sat in front of the bezel and obscured the original LCD effect.

## Decision

- Mount one world-space widget on each built device. Fit it to the bezel behind clear glass and use the stock fishing-winch LCD material for scanlines and distortion. Update through the game thread when the displayed values or locale change. The widget remains on the device and can update without focus.
- Show catch weight, current net limit and fill, electrical draw, and saved automation state. Keep the cabinet weight indicator on the separate Advanced gauge and keep direct raising and lowering on the stock lever.
- Route the stock mapped **Interact** action by the live target. The screen opens the close camera view and enables one on-screen control. Advanced casing opens its stock inventory. The socket answers to native cable interaction. Keep the display, socket, and cabinet from consuming the same press. **Esc** restores the camera and returns input to the game.
- Show the current state above the action button. An enabled device presents a green **Turn off** button, and a disabled one presents a red **Turn on** button. The label describes the next action.
- Share one translation table between the two devices, follow the game's active language and number locale, and support the 14 shipped game languages. Choose units based on the actual weight scale, including grams and tonnes where needed. Use the stock no-power string when available and the local translation as a fallback.
- At zero stored electricity on a known receiver, replace the whole control face with a centered low-power warning, hide the input target, and pulse the red bolt in a GPU material. A disconnected receiver with charge still displays its readings. A live cable can charge the empty receiver and restore the button without turning automation on.

## Consequences

The visible display and the focus session have separate lifetimes. Closing the close view releases camera and input while preserving the same device readout. One interaction target consumes the press and one localized control surface supports both variants.

## Verification

Development game checks on both models covered the close camera, values updating after the player walked away, the view under an oblique angle, and the warning at zero charge. The final button behavior was exercised in dev.37. Regression tests cover off-focus redraw, language and regional aliases, live capacity, empty-buffer handling, and interaction routing. [World screen](../../../src/ShipNetAutomation/Scripts/shipnet/world_screen.lua) · [Localization](../../../src/ShipNetAutomation/Scripts/shipnet/screen_text.lua) · [Screen tests](../../../tests/test_world_screen.py) · [Interaction tests](../../../tests/test_interaction.py)
