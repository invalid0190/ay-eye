import ast
from pathlib import Path


def _find_function(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Function not found: {name}")


def main():
    path = Path("core/engine/executor.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    execute_single = _find_function(tree, "execute_single")

    local_live_perception_imports = []
    for node in ast.walk(execute_single):
        if isinstance(node, ast.ImportFrom) and node.module == "core.vision.live_perception":
            for alias in node.names:
                if alias.asname == "live_perception" or alias.name == "live_perception":
                    local_live_perception_imports.append(node.lineno)

    if local_live_perception_imports:
        raise AssertionError(
            "execute_single must use the module-level live_perception import; "
            f"local import shadows it at lines {local_live_perception_imports}"
        )

    module_level_import = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "core.vision.live_perception"
        and any(alias.name == "live_perception" for alias in node.names)
        for node in tree.body
    )
    if not module_level_import:
        raise AssertionError("executor.py must keep a module-level live_perception import")

    print("[PASS] execute_single live_perception scope is safe")


if __name__ == "__main__":
    main()
