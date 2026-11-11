import json
import sys
import zipfile
from pathlib import Path


def top_level_json(names, folder):
    return [
        name for name in names
        if f"/{folder}/" in name and name.endswith(".json") and len(name.split("/")) == 4
    ]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def token_names(node, prefix=""):
    if not isinstance(node, dict):
        return set()
    if "$value" in node:
        return {prefix}
    names = set()
    for key, value in node.items():
        if not key.startswith("$"):
            names.update(token_names(value, f"{prefix}.{key}" if prefix else key))
    return names


def main():
    root = Path(__file__).resolve().parent
    source = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root / "case-library.penpot"
    inventory = json.loads((root / "ui-inventory.json").read_text(encoding="utf-8"))
    index = json.loads((root / "board-index.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(source) as archive:
        corrupt = archive.testzip()
        if corrupt:
            raise RuntimeError(f"Penpot 导出包损坏：{corrupt}")
        names = archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))
        file_id = manifest["files"][0]["id"]
        if file_id != inventory["source"]["penpotFileId"]:
            raise RuntimeError("导出包不是当前设计文件")
        token_files = [name for name in names if name.endswith("/tokens.json")]
        if len(token_files) != 1:
            raise RuntimeError(f"预期一个 tokens.json，实际找到 {len(token_files)} 个")
        tokens = json.loads(archive.read(token_files[0]))
        pages = [json.loads(archive.read(name)) for name in top_level_json(names, "pages")]
        components = [json.loads(archive.read(name)) for name in top_level_json(names, "components")]
        target_pages = ["组件 · 统一设计系统", *dict.fromkeys(board["page"] for board in index["boards"])]
        expected_pages = [*inventory["existingPages"], *target_pages]
        page_names = [page["name"] for page in pages]
        if len(pages) != len(expected_pages) or set(page_names) != set(expected_pages):
            raise RuntimeError(f"页面不符合清单：{page_names}")
        expected_components = inventory["source"]["existingComponentCount"] + len(inventory["source"]["sharedComponents"])
        if len(components) != expected_components:
            raise RuntimeError(f"组件数量应为 {expected_components}，实际为 {len(components)}")
        shared_names = [component.get("name", "").rsplit(" / ", 1)[-1] for component in components]
        missing_components = [name for name in inventory["source"]["sharedComponents"] if shared_names.count(name) != 1]
        if missing_components:
            raise RuntimeError(f"共享组件缺失或重复：{missing_components}")
        actual_tokens = set()
        for token_set in tokens.values():
            actual_tokens.update(token_names(token_set))
        expected_tokens = {
            "color.surface", "color.surfaceInk", "color.surfaceMuted", "color.surfaceSubtle",
            "color.surfaceLine", "radius.panel", "space.44", "space.56",
        }
        if not expected_tokens.issubset(actual_tokens):
            raise RuntimeError(f"缺少 tokens：{sorted(expected_tokens - actual_tokens)}")
        expected_boards = {board["fullName"]: board for board in index["boards"]}
        actual_boards = []
        for page in pages:
            if page["name"] not in target_pages:
                continue
            prefix = f"files/{file_id}/pages/{page['id']}/"
            root_shape = json.loads(archive.read(prefix + "00000000-0000-0000-0000-000000000000.json"))
            for shape_id in root_shape.get("shapes", []):
                shape = json.loads(archive.read(prefix + shape_id + ".json"))
                if shape.get("name") in expected_boards:
                    actual_boards.append({"name": shape["name"], "id": shape["id"], "page": page["name"]})
        missing_boards = sorted(set(expected_boards) - {board["name"] for board in actual_boards})
        mismatched_boards = [
            board["name"] for board in actual_boards
            if expected_boards[board["name"]]["id"] != board["id"]
            or expected_boards[board["name"]]["page"] != board["page"]
        ]
        if len(actual_boards) != len(expected_boards) or missing_boards or mismatched_boards:
            raise RuntimeError(json.dumps({"missing": missing_boards, "mismatched": mismatched_boards}, ensure_ascii=False))
        contents = {
            "pages": sorted(pages, key=lambda page: page.get("index", 0)),
            "components": [
                {"id": component.get("id"), "name": component.get("name")}
                for component in components
            ],
        }
        write_json(root / "tokens.json", tokens)
        write_json(root / "penpot-manifest.json", manifest)
        write_json(root / "penpot-contents.json", contents)
        print(json.dumps({
            "sourceBytes": source.stat().st_size,
            "archiveEntries": len(names),
            "pageCount": len(pages),
            "pageNames": [page["name"] for page in contents["pages"]],
            "componentCount": len(components),
            "boardCount": len(actual_boards),
            "tokenCount": len(actual_tokens),
            "tokenFile": token_files[0],
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
