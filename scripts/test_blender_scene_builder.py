from core.engine.blender_scene_builder import build_enhance_script, build_scene_script


def test_case(name, description, expected_terms):
    code = build_scene_script(description, "")
    compile(code, f"<{name}>", "exec")
    missing = [term for term in expected_terms if term not in code]
    if missing:
        raise AssertionError(f"{name}: missing {missing}")
    print(f"[PASS] {name}: {len(code)} chars")


def assert_not_contains(name, code, forbidden_terms):
    present = [term for term in forbidden_terms if term in code]
    if present:
        raise AssertionError(f"{name}: should not contain {present}")
    print(f"[PASS] {name}: avoided stale template terms")


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
    spaceship_code = build_scene_script(
        "create a sci-fi spaceship like this reference image",
        "sleek triangular spacecraft with glowing cockpit, swept wings, and rear thrusters",
    )
    compile(spaceship_code, "<spaceship reference>", "exec")
    if "sleek spacecraft fuselage" not in spaceship_code:
        raise AssertionError("spaceship reference: missing spaceship-specific profile")
    assert_not_contains(
        "spaceship reference",
        spaceship_code,
        ["shipping container cafe body", "AYEYE_MLO_SCENE_CREATED", "MLO main floor slab"],
    )

    plain_cafe_code = build_scene_script(
        "create a cozy coffee shop interior from this reference image",
        "warm interior counter, menu board, shelves, round tables, chairs, pendant lights",
    )
    compile(plain_cafe_code, "<plain cafe interior>", "exec")
    if "interior service counter" not in plain_cafe_code:
        raise AssertionError("plain cafe interior: missing generic interior profile")
    assert_not_contains(
        "plain cafe interior",
        plain_cafe_code,
        ["shipping container cafe body", "AYEYE_MLO_SCENE_CREATED", "MLO main floor slab"],
    )

    restaurant_code = build_scene_script(
        "create a restaurant interior from the image reference",
        "tables, chairs, service counter, wall menu, warm lights",
    )
    compile(restaurant_code, "<restaurant without MLO>", "exec")
    assert_not_contains(
        "restaurant without explicit MLO",
        restaurant_code,
        ["AYEYE_MLO_SCENE_CREATED", "MLO room volume guide", "collision proxy guide"],
    )

    gta_vehicle_code = build_scene_script(
        "create a GTA style sports car from this reference image",
        "low blue car body, black wheels, orange light strips",
    )
    compile(gta_vehicle_code, "<gta vehicle without MLO>", "exec")
    if "vehicle main body shell" not in gta_vehicle_code:
        raise AssertionError("gta vehicle reference: missing vehicle profile")
    assert_not_contains(
        "gta vehicle without explicit MLO",
        gta_vehicle_code,
        ["AYEYE_MLO_SCENE_CREATED", "MLO main floor slab", "MLO room volume guide"],
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
