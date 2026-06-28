"""Verify house-exit evidence from saves/ or recent runner logs."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from src.state.gold_state_reader import MAP_KEY_NEW_BARK_TOWN

ROOT = Path(__file__).resolve().parents[1]
SAVE_DIR = ROOT / "saves"
LOG_GLOB = "cli_house_v*.log"
def _default_log_dir() -> Path:
    if env := os.environ.get("HOUSE_EXIT_LOG_DIR"):
        return Path(env)
    return ROOT / "data" / "house_exit_logs"


def _latest_final_save() -> Path | None:
    saves = sorted(SAVE_DIR.glob("final_*.state"), key=lambda p: p.stat().st_mtime, reverse=True)
    return saves[0] if saves else None


def _check_save(path: Path) -> tuple[str, tuple[int, int]] | None:
    from src.emulator.pyboy_wrapper import PyBoyWrapper
    from src.state.gold_state_reader import MAP_KEY_NEW_BARK_TOWN as NB

    rom_candidates = [
        Path("roms/pokemon_silver.gbc"),
        Path(
            "roms/Pokemon - Silver Version (USA, Europe) (SGB Enhanced) (GB Compatible).gbc"
        ),
    ]
    rom = next((p for p in rom_candidates if p.exists()), None)
    if rom is None:
        return None
    with PyBoyWrapper(rom, window="null") as emu:
        emu.load_state(path.stem)
        gs = emu.get_game_state()
        return gs.map_key, (gs.player.x, gs.player.y)


def _parse_logs(scratch: Path) -> list[str]:
    hits: list[str] = []
    pattern = re.compile(
        r"(MILESTONE: Left house|Left house — New Bark Town|Final: New Bark Town \(24:4\)|map: 24:[467] )"
    )
    for log in sorted(scratch.glob(LOG_GLOB)):
        for line in log.read_text().splitlines():
            if pattern.search(line):
                hits.append(f"{log.name}: {line.strip()}")
    return hits


def main() -> int:
    scratch = _default_log_dir()
    save = _latest_final_save()
    ok = False

    if save:
        print(f"Latest save: {save.name}")
        try:
            result = _check_save(save)
            if result:
                map_key, pos = result
                print(f"  map_key={map_key} position={pos}")
                if map_key == MAP_KEY_NEW_BARK_TOWN:
                    ok = True
                    print("  PASS: player on New Bark Town exterior")
                else:
                    print(f"  FAIL: expected {MAP_KEY_NEW_BARK_TOWN}")
        except Exception as exc:
            print(f"  Could not load save: {exc}")

    log_hits = _parse_logs(scratch)
    if log_hits:
        print("Log evidence:")
        for hit in log_hits[:10]:
            print(f"  {hit}")
        if any("Left house" in h or "24:4" in h for h in log_hits):
            ok = True

    if not ok:
        print("No house-exit evidence found in saves or logs", file=sys.stderr)
        return 1
    print("House exit state check: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())