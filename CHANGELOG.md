# Changelog

## 1.2.0

### Fixed
- **Game lag with live sync on.** The pulsing "Live sync on" dot kept the app redrawing on the
  graphics card non-stop, which took frames from the game. It now glows steadily and blinks once
  when a sync lands.

### Changed
- Live sync does nothing while the window is minimised or hidden to the tray, and catches up the
  moment it is shown again.
- The save is read at Windows background priority, and 6 seconds after the game saves instead
  of 2, so the game always comes first.

## 1.1.0

### New
- **Repairs tick off one slot at a time.** A part listed as ×4 now shows "1/4 repaired" with its
  own progress bar, and buttons for "Fixed 1", "All 4 fixed" and "Undo 1". The Collect List only
  asks for materials for the slots still broken, and "use materials" removes one slot's worth.
- **Live sync with your save.** Tick "Keep in sync while I play" on the Import page and the tracker
  re-reads your save a few seconds after the game writes it: inventory, and repairs on ships you
  already track. The save is still only ever read, never changed.
- **Pages update in place.** Numbers change on the Collect List, item pages, Goals, Overview and
  the sidebar without reloading, keeping your filter, scroll position and anything you are typing.
- **Where to find it.** Rarity and location notes from the No Man's Sky Wiki on item pages and on
  every Collect List row, a "hard to find" tag, and a "Hard to find" filter on the Collect List.

### Changed
- Clicking a broken part that is already listed raises its count instead of adding a second card.
- A ship imported from the auto save is recognised when the manual save of the same slot is newer.
- Changing a "You have" number re-works the whole Collect List, so owning a crafted part lowers
  what its ingredients need.

### Credits
- Location notes: No Man's Sky Wiki (nomanssky.fandom.com), text licensed CC BY-SA 3.0.

## 1.0.0
- First release: materials, recipes, goals, ship repairs, read-only save import.
