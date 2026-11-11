import json
from pathlib import Path
from generate_ui import PAGE_BY_FLOW, RENDER, board_specs, execute
from mcp_client import McpClient


def main():
    root = Path(__file__).resolve().parent
    inventory = json.loads((root / "ui-inventory.json").read_text(encoding="utf-8"))
    client = McpClient()
    slots = {}
    indexed = []
    missing = []
    duplicates = []
    misplaced = []
    geometry_errors = []
    overflowing = []
    specs_by_page = {}
    flow_indices = {}
    expected_names = set()
    for flow in inventory["flows"]:
        page = PAGE_BY_FLOW[flow["id"]]
        slot = slots.get(page, 0)
        specs = board_specs(flow, page, slot)
        slots[page] = slot + len(specs)
        specs_by_page.setdefault(page, []).extend(specs)
        for flow_index, spec in enumerate(specs, 1):
            expected_names.add(spec["fullName"])
            flow_indices[spec["fullName"]] = flow_index

    for page, specs in specs_by_page.items():
        expected_on_page = {spec["fullName"]: True for spec in specs}
        code = f"""
          {RENDER}
          await ensurePage({json.dumps(page, ensure_ascii=False)});
          return penpot.currentPage.root.children.map(shape => ({{ id: shape.id, name: shape.name, x: shape.x, y: shape.y, width: shape.width, height: shape.height }}));
        """
        shapes = execute(client, code)
        for spec in specs:
            matches = [shape for shape in shapes if shape["name"] == spec["fullName"]]
            if len(matches) > 1:
                duplicates.append(spec["fullName"])
            if not matches:
                missing.append(spec["fullName"])
                continue
            shape = matches[0]
            expected_geometry = [spec["x"], spec["y"], *map(int, spec["viewport"].split("x"))]
            actual_geometry = [shape[key] for key in ("x", "y", "width", "height")]
            if any(abs(actual - expected) > 0.01 for actual, expected in zip(actual_geometry, expected_geometry)):
                geometry_errors.append({"name": spec["fullName"], "expected": expected_geometry, "actual": actual_geometry})
            indexed.append({**spec, **shape, "page": page, "flowIndex": flow_indices[spec["fullName"]]})
        for shape in shapes:
            if shape["name"] in expected_names and shape["name"] not in expected_on_page:
                misplaced.append({"name": shape["name"], "actualPage": page})
        overflow_code = f"""
          const expected = {json.dumps(expected_on_page, ensure_ascii=False)};
          return penpot.currentPage.root.children.flatMap(board => {{
            if (!Object.hasOwn(expected, board.name)) return [];
            return penpotUtils.analyzeDescendants(board, (root, shape) => {{
              if (shape.hidden || penpotUtils.isContainedIn(shape, board)) return null;
              return {{ board: board.name, id: shape.id, name: shape.name, type: shape.type }};
            }}).map(item => item.result);
          }});
        """
        overflowing.extend(execute(client, overflow_code))

    expected_tokens = [
        "color.surface", "color.surfaceInk", "color.surfaceMuted",
        "color.surfaceSubtle", "color.surfaceLine", "radius.panel", "space.44", "space.56",
    ]
    token_code = f"return {json.dumps(expected_tokens)}.filter(name => !penpotUtils.findTokenByName(name));"
    missing_tokens = execute(client, token_code)
    component_checks = execute(client, """
      const components = penpot.library.local.components.filter(component => ['Site Header', 'Admin Navigation', 'Search Field'].includes(component.name));
      const header = components.find(component => component.name === 'Site Header');
      const navigation = components.find(component => component.name === 'Admin Navigation');
      return {
        names: components.map(component => component.name),
        paths: components.map(component => component.path),
        headerLogo: Boolean(header?.mainInstance().children.some(shape => shape.name === '上海大学校标')),
        navigationItems: navigation?.mainInstance().children.filter(shape => shape.name.startsWith('管理导航-')).length || 0,
      };
    """)
    result = {
        "boardCount": len(indexed),
        "expectedBoardCount": len(expected_names),
        "issueCount": len({issue for flow in inventory["flows"] for issue in flow["issues"]}),
        "flowCount": len(inventory["flows"]),
        "missingBoards": missing,
        "duplicateBoards": sorted(set(duplicates)),
        "misplacedBoards": misplaced,
        "geometryErrors": geometry_errors,
        "overflowingShapes": overflowing,
        "missingTokens": missing_tokens,
        "components": component_checks["names"],
        "componentChecks": component_checks,
        "boards": indexed,
    }
    (root / "board-index.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in result.items() if key != "boards"}, ensure_ascii=False, indent=2))
    components_valid = (
        len(component_checks["names"]) == 3
        and component_checks["headerLogo"]
        and component_checks["navigationItems"] == 8
        and all(path == "UI" for path in component_checks["paths"])
    )
    if missing or duplicates or misplaced or geometry_errors or overflowing or missing_tokens or not components_valid or len(indexed) != len(expected_names):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
