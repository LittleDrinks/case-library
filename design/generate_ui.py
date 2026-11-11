import json
import sys
from pathlib import Path
from mcp_client import McpClient


ROOT = Path(__file__).resolve().parent
RENDER = (ROOT / "penpot_render.js").read_text(encoding="utf-8")
PAGE_BY_FLOW = {
    "foundation": "扩展 · 01 核心与发现",
    "collections": "扩展 · 01 核心与发现",
    "preferences": "扩展 · 01 核心与发现",
    "search-metadata": "扩展 · 01 核心与发现",
    "favorites": "扩展 · 01 核心与发现",
    "create-submission": "扩展 · 01 核心与发现",
    "relationships": "扩展 · 01 核心与发现",
    "admin-stats": "扩展 · 02 管理与账号",
    "accounts": "扩展 · 02 管理与账号",
    "restricted-sharing": "扩展 · 02 管理与账号",
    "announcements": "扩展 · 02 管理与账号",
    "source-review": "扩展 · 02 管理与账号",
    "materials": "扩展 · 03 素材与交付",
    "teaching-pack": "扩展 · 03 素材与交付",
    "document-extract": "扩展 · 03 素材与交付",
    "self-check": "扩展 · 04 工作台增强",
    "conversation-export": "扩展 · 04 工作台增强",
    "web-sources": "扩展 · 04 工作台增强",
    "ai-expanded": "扩展 · 04 工作台增强",
    "selection-comments": "扩展 · 04 工作台增强",
    "word-templates": "扩展 · 04 工作台增强",
    "version-snapshot": "扩展 · 04 工作台增强",
    "motion": "扩展 · 05 动效与状态",
}


def execute(client, code):
    result = client.call_tool("execute_code", {"code": code})
    text = result["content"][0]["text"]
    if "Tool execution failed" in text:
        raise RuntimeError(text)
    return json.loads(text)["result"]


def board_specs(flow, page, slot):
    specs = []
    issue_suffix = ",".join(f"#{issue}" for issue in flow["issues"])
    for board in flow["boards"]:
        current = slot + len(specs)
        specs.append({
            "flow": flow["id"],
            "flowTitle": flow["title"],
            "status": flow["status"],
            "name": board["name"],
            "fullName": f"【{flow['title']}】{board['name']} · {issue_suffix}",
            "layout": board["layout"],
            "viewport": board.get("viewport", "1440x1000"),
            "x": 200 + (current % 3) * 1540,
            "y": 200 + (current // 3) * 1120,
        })
    return specs


def prepare_campus(client, page):
    execute(client, f"{RENDER}\nreturn (await ensurePage({json.dumps(page, ensure_ascii=False)})).name;")
    execute(client, "storage.campusImages = {}; return true;")
    for variant in ("desktop", "mobile"):
        client.call_tool("import_image", {
            "filePath": str(ROOT / f"assets/shu-campus-{variant}.webp"),
            "x": -100000, "y": -100000,
        })
        execute(client, f"storage.campusImages[{json.dumps(variant)}] = penpot.currentPage.root.children.at(-1); return storage.campusImages[{json.dumps(variant)}].id;")


def main():
    inventory = json.loads((ROOT / "ui-inventory.json").read_text(encoding="utf-8"))
    selected = set(sys.argv[1:])
    client = McpClient()
    slots = {}
    completed = []
    for flow in inventory["flows"]:
        page = PAGE_BY_FLOW[flow["id"]]
        slot = slots.get(page, 0)
        specs = board_specs(flow, page, slot)
        slots[page] = slot + len(specs)
        if selected and flow["id"] not in selected:
            continue
        if flow["id"] in ("foundation", "motion"):
            prepare_campus(client, page)
        result = {"page": page, "created": [], "skipped": []}
        for spec in specs:
            code = f"""
              {RENDER}
              return await renderFlow({json.dumps(page, ensure_ascii=False)}, {json.dumps([spec], ensure_ascii=False)});
            """
            current = execute(client, code)
            result["created"].extend(current["created"])
            result["skipped"].extend(current["skipped"])
        if flow["id"] in ("foundation", "motion"):
            execute(client, "if (storage.campusImages) Object.values(storage.campusImages).forEach(image => image.remove()); delete storage.campusImages; if (storage.campusImage) storage.campusImage.remove(); delete storage.campusImage; return true;")
        completed.append({"flow": flow["id"], **result})
        print(json.dumps({"flow": flow["id"], "created": len(result["created"]), "skipped": len(result["skipped"])}, ensure_ascii=False), flush=True)
    print(json.dumps({"flows": len(completed), "created": sum(len(item["created"]) for item in completed), "skipped": sum(len(item["skipped"]) for item in completed)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
