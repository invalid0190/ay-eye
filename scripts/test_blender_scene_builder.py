from core.engine.blender_scene_builder import build_enhance_script, build_scene_script


def test_case(name, description, expected_terms):
    code = build_scene_script(description, "")
    compile(code, f"<{name}>", "exec")
    missing = [term for term in expected_terms if term not in code]
    if missing:
        raise AssertionError(f"{name}: missing {missing}")
    print(f"[PASS] {name}: {len(code)} chars")


def main():
    test_case(
        "container cafe",
        "professional detailed container cafe MLO with portal collision helpers",
        ["AYEYE_SCENE_CREATED", "MLO portal guide", "espresso machine"],
    )
    test_case(
        "garage MLO",
        "create a mechanic garage MLO with rooms portals and collision",
        ["AYEYE_MLO_SCENE_CREATED", "hydraulic vehicle lift", "MLO portal guide"],
    )
    test_case(
        "house MLO",
        "create a house interior MLO from reference image",
        ["AYEYE_MLO_SCENE_CREATED", "living room", "bedroom bed"],
    )
    test_case(
        "warehouse MLO",
        "create a warehouse loading bay MLO",
        ["AYEYE_MLO_SCENE_CREATED", "pallet rack", "truck loading bay portal"],
    )
    enhance_code = build_enhance_script(
        "make the existing container cafe MLO professional with more details",
        "preserve scene, add details, verify room portals collision",
    )
    compile(enhance_code, "<enhance existing MLO>", "exec")
    missing = [
        term for term in (
            "AYEYE_ENHANCEMENT_RESULT",
            "enhanced MLO fallback room volume guide",
            "portal lintel frame",
            "Ay-Eye enhancement checklist board",
        )
        if term not in enhance_code
    ]
    if missing:
        raise AssertionError(f"enhance existing MLO: missing {missing}")
    print(f"[PASS] enhance existing MLO: {len(enhance_code)} chars")

    print("\n=== Blender scene builder tests passed ===")


if __name__ == "__main__":
    main()
