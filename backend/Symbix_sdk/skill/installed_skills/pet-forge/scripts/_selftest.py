"""离线自测:不调用 LLM。类级断言,不碰 skill 目录(全部写临时目录)。

用法:python scripts/_selftest.py         退出码 0 = 全过
覆盖:validate_rig 像素契约(正/负例 + legacy 画板只降级为 warning)、derive_mirrors、
      validate_states 白名单、pack_theme 产物三件套。
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))

from derive_mirrors import derive_mirrors  # noqa: E402
from pack_theme import pack_from_files  # noqa: E402
from validate_rig import split_levels, validate_rig, validate_rig_file  # noqa: E402
from validate_states import validate_states, validate_states_file  # noqa: E402

ROOT = _SCRIPTS.parent
FIX = ROOT / "assets" / "fixtures"


def main() -> int:
    # positive: fixture rig
    errs = validate_rig_file(FIX / "base.svg")
    assert not errs, errs
    print("OK validate_rig fixture")

    # 像素画板契约:像素模板 rig 必须干净通过
    px_text = (FIX / "pixel-base.svg").read_text(encoding="utf-8")
    px_errs, px_warns = split_levels(validate_rig(px_text, pixel=True))
    assert not px_errs, px_errs
    assert not px_warns, px_warns
    print("OK validate_rig pixel fixture")

    # 老画板 200x200 仍可用:只降级为 warning(0.96 倍缩进帧),不能报 error
    legacy_text = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">'
                   '<rect x="10" y="10" width="40" height="40" fill="var(--x)"/></svg>')
    legacy_ok, legacy_warn = split_levels(validate_rig(legacy_text, pixel=True))
    assert not [e for e in legacy_ok if str(e.get("rule", "")).startswith("pixel_")], legacy_ok
    assert any(w.get("rule") == "pixel_board_legacy" for w in legacy_warn), legacy_warn
    # 非像素契约(平滑模式)下不该出现这个提示
    assert not any(str(e.get("rule", "")) == "pixel_board_legacy" for e in validate_rig(legacy_text)), legacy_text
    print("OK validate_rig legacy board warns only")

    # 推荐画板(帧尺寸)必须通过 viewBox 校验
    errs = validate_rig('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 208"></svg>')
    assert not any(e.get("rule") == "viewBox" for e in errs), errs
    print("OK viewBox frame-sized accepted")

    # 像素契约必须真的在拦:平滑 fixture 在 pixel=True 下要报错
    sm_errs, sm_warns = split_levels(validate_rig((FIX / "base.svg").read_text(encoding="utf-8"), pixel=True))
    assert any(e.get("rule") == "pixel_curve" for e in sm_errs), sm_errs
    assert any(e.get("rule") == "pixel_round" for e in sm_warns), sm_warns
    print("OK validate_rig pixel contract rejects smooth rig")

    # 小数坐标 / 曲线 / 渐变的负例
    bad_grid = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"><rect x="1.5" y="1" width="4" height="4" fill="var(--x)"/></svg>'
    assert any(e.get("rule") == "pixel_grid" for e in validate_rig(bad_grid, pixel=True))
    bad_curve = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"><path d="M1 1 Q2 2 3 1" fill="var(--x)"/></svg>'
    assert any(e.get("rule") == "pixel_curve" for e in validate_rig(bad_curve, pixel=True))
    bad_grad = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"><linearGradient id="g"/></svg>'
    assert any(e.get("rule") == "pixel_unsupported" for e in validate_rig(bad_grad, pixel=True))
    assert not any(str(e.get("rule", "")).startswith("pixel_") for e in validate_rig(bad_curve, pixel=False)), \
        "pixel=False 时不该跑像素契约"
    print("OK validate_rig pixel negatives")

    # negative: bad viewBox
    errs = validate_rig('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"></svg>')
    assert any(e.get("rule") == "viewBox" for e in errs), errs
    print("OK neg viewBox")

    # mirrors
    d = derive_mirrors({"idle": {"eye-right": "blink 1s ease-in-out infinite"}})
    assert "eye-left" in d["idle"], d
    print("OK derive_mirrors")

    # negative: unknown anim
    errs = validate_states(
        {"idle": {"body": "fly 1s ease 1"}},
        part_ids=["body"],
        require_all_states=False,
        check_mirrors=False,
    )
    assert errs, "expected anim error"
    print("OK neg anim whitelist:", errs[0]["message"])

    # 镜像后的 states + pack:全部写临时目录
    # (镜像结果是派生物,不再落 assets/fixtures/,免得 skill 目录被写脏、也免得误入库)
    import tempfile
    from derive_mirrors import main as dm_main

    with tempfile.TemporaryDirectory(prefix="pet_forge_selftest_") as tmp:
        out = Path(tmp)
        mirrored = out / "states.mirrored.json"
        assert dm_main([str(FIX / "states.json"), "-o", str(mirrored)]) == 0
        errs = validate_states_file(mirrored, rig_svg_path=FIX / "base.svg")
        assert not errs, errs
        print("OK validate_states mirrored")

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
