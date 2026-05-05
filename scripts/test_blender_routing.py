from types import SimpleNamespace

from core.engine.brain import Brain
from core.engine.skill_manager import skill_manager


def assert_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")
    print(f"[PASS] {label}")


def assert_true(value, label):
    if not value:
        raise AssertionError(label)
    print(f"[PASS] {label}")


def main():
    brain = Brain()
    overlay_state = SimpleNamespace(app="AY-EYE", window="AY-EYE overlay")

    bad_sollumz_response = {
        "intent": "act",
        "status": "in_progress",
        "message": "I'm setting up the Blender scene with the Sollumz property for the cafe container.",
        "confidence": 0.95,
        "actions": [
            {
                "type": "blender_python",
                "description": "set Sollumz property for the cafe container",
                "script": "import bpy\nbpy.context.scene.sollumz_type = 'DRAWABLE'",
                "expect": {"type": "none"},
            }
        ],
        "plan": ["Use Blender Python to create the cafe container."],
    }
    normalized = brain._normalize_blender_task(
        bad_sollumz_response,
        "create something like this cafe container",
        overlay_state,
    )
    assert_equal(
        [a.get("type") for a in normalized["actions"]],
        ["hotkey", "blender_create_scene"],
        "generic cafe creation redirects away from Sollumz blender_python",
    )
    assert_equal(
        normalized["actions"][1]["expect"]["type"],
        "blender_scene_objects",
        "scene creation requires Blender object verification",
    )

    stale_template_response = {
        "intent": "act",
        "status": "in_progress",
        "message": "I'll use Blender Python to create a sci-fi spaceship model.",
        "confidence": 0.95,
        "actions": [
            {
                "type": "blender_python",
                "description": "create the reference model",
                "script": "import bpy\nprint('create')",
                "expect": {"type": "none"},
            }
        ],
        "plan": ["Use Blender Python for the model."],
    }
    fresh_reference = brain._normalize_blender_task(
        stale_template_response,
        "create a sci-fi spaceship like this reference image",
        overlay_state,
    )
    assert_equal(
        [a.get("type") for a in fresh_reference["actions"]],
        ["hotkey", "blender_create_scene"],
        "fresh non-container reference uses scene builder",
    )
    fresh_description = fresh_reference["actions"][1]["description"].lower()
    assert_true(
        "container cafe" not in fresh_description and "portal guides" not in fresh_description,
        "fresh scene description does not inject stale container/MLO template text",
    )

    mlo_blockout_response = {
        "intent": "act",
        "status": "in_progress",
        "message": "I'll set up the Sollumz MLO properties.",
        "confidence": 0.95,
        "actions": [
            {
                "type": "blender_python",
                "description": "set Sollumz MLO room and portal properties",
                "script": "import bpy\nprint('sollumz setup')",
                "expect": {"type": "none"},
            }
        ],
        "plan": ["Use Blender Python for Sollumz MLO metadata."],
    }
    mlo_blockout = brain._normalize_blender_task(
        mlo_blockout_response,
        "create a FiveM MLO room with Sollumz portals",
        overlay_state,
    )
    assert_equal(
        [a.get("type") for a in mlo_blockout["actions"]],
        ["hotkey", "blender_create_scene"],
        "creative MLO requests use the scene builder with guide objects",
    )

    detail_response = {
        "intent": "act",
        "status": "in_progress",
        "message": "I'll run Blender Python to add more details.",
        "confidence": 0.95,
        "actions": [
            {
                "type": "blender_python",
                "description": "add detail objects to current MLO scene",
                "script": "import bpy\nprint('detail pass')",
                "expect": {"type": "none"},
            }
        ],
        "plan": ["Use Blender Python for scene details."],
    }
    enhanced = brain._normalize_blender_task(
        detail_response,
        "make this MLO professional and add more details",
        overlay_state,
    )
    assert_equal(
        [a.get("type") for a in enhanced["actions"]],
        ["hotkey", "blender_enhance_scene"],
        "existing-scene detail requests use the non-destructive enhancer",
    )
    assert_equal(
        enhanced["actions"][1]["expect"]["type"],
        "blender_scene_objects",
        "enhancement requires Blender object verification",
    )

    export_response = {
        "intent": "act",
        "status": "in_progress",
        "message": "I'll set up the Sollumz export properties.",
        "confidence": 0.95,
        "actions": [
            {
                "type": "blender_python",
                "description": "set Sollumz YMAP export properties",
                "script": "import bpy\nprint('sollumz export setup')",
                "expect": {"type": "none"},
            }
        ],
        "plan": ["Use Blender Python for explicit export metadata."],
    }
    export = brain._normalize_blender_task(
        export_response,
        "set Sollumz YMAP export properties for this MLO",
        overlay_state,
    )
    assert_equal(
        [a.get("type") for a in export["actions"]],
        ["blender_python"],
        "explicit export/property request keeps the Sollumz workflow",
    )

    bad_status_response = {
        "intent": "guide",
        "status": "complete",
        "message": "I can't see any information indicating Blender is open through the MCP server.",
        "confidence": 0.9,
        "actions": [],
        "plan": [],
    }
    status_check = brain._normalize_blender_task(
        bad_status_response,
        "Can you see Blender is opened through MCP Server?",
        overlay_state,
    )
    assert_equal(
        [a.get("type") for a in status_check["actions"]],
        ["blender_bridge_status"],
        "MCP/bridge status questions check the local bridge instead of guessing",
    )
    assert_equal(
        status_check["status"],
        "in_progress",
        "bridge status check waits for executor evidence",
    )

    generic_skills = skill_manager.get_all_skills_context(
        "create a container cafe in Blender",
        active_app="blender",
        active_window="Blender",
    )
    assert_true(
        "blender_sollumz" not in generic_skills,
        "generic Blender prompts do not inject the Sollumz skill",
    )

    sollumz_skills = skill_manager.get_all_skills_context(
        "create a FiveM MLO with Sollumz ymap collision",
        active_app="blender",
        active_window="Blender",
    )
    assert_true(
        "blender_sollumz" in sollumz_skills,
        "explicit Sollumz prompts inject the Sollumz skill",
    )

    print("\n=== Blender routing tests passed ===")


if __name__ == "__main__":
    main()
