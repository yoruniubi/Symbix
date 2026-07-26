"""离线自测：不调用 LLM。"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))

from derive_mirrors import derive_mirrors  # noqa: E402
from pack_theme import pack_from_files  # noqa: E402
from validate_rig import validate_rig, validate_rig_file  # noqa: E402
from validate_states import validate_states, validate_states_file  # noqa: E402

ROOT = _SCRIPTS.parent
FIX = ROOT / "assets" / "fixtures"


def main() -> int:
    # positive: fixture rig
    errs = validate_rig_file(FIX / "base.svg")
    assert not errs, errs
    print("OK validate_rig fixture")

    # negative: bad viewBox
    errs = validate_rig('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"></svg>')
    assert any(e.get("rule") == "viewBox" for e in errs), errs
    print("OK neg viewBox")

    # mirrors
    d = derive_mirrors({"idle": {"eye-right": "blink 1s ease-in-out infinite"}})
    assert "eye-left" in d["idle"], d
    print("OK derive_mirrors")

    # positive states after mirror
    mirrored = FIX / "states.mirrored.json"
    if not mirrored.is_file():
        from derive_mirrors import main as dm_main

        dm_main([str(FIX / "states.json"), "-o", str(mirrored)])
    errs = validate_states_file(mirrored, rig_svg_path=FIX / "base.svg")
    assert not errs, errs
    print("OK validate_states mirrored")

    # negative: unknown anim
    errs = validate_states(
        {"idle": {"body": "fly 1s ease 1"}},
        part_ids=["body"],
        require_all_states=False,
        check_mirrors=False,
    )
    assert errs, "expected anim error"
    print("OK neg anim whitelist:", errs[0]["message"])

    # pack
    out = FIX / "packed"
    theme = pack_from_files(
        name="Fixture Cat",
        rig_path=FIX / "base.svg",
        states_path=mirrored,
        out_dir=out,
        schema_path=ROOT / "assets" / "theme.schema.json",
    )
    assert (out / "base.svg").is_file()
    assert (out / "states.json").is_file()
    assert (out / "theme.json").is_file()
    assert "core_animation" in theme["capabilities"]
    print("OK pack_theme", theme["capabilities"])

    print("ALL SELFTESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
