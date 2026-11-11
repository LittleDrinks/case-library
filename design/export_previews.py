import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from generate_ui import RENDER, execute
from mcp_client import McpClient


def capture(board, output, space_id):
    output = Path(output).resolve()
    code = f"""
      {RENDER}
      await ensurePage({json.dumps(board['page'], ensure_ascii=False)});
      const board = penpot.currentPage.root.children.find(shape => shape.id === {json.dumps(board['id'])});
      if (!board) throw new Error('画板不存在');
      return penpot.generateMarkup([board], {{ type: 'svg' }});
    """
    svg = execute(board["client"], code)
    if not svg.startswith("<svg"):
        raise RuntimeError("Penpot 没有返回有效 SVG")
    document = ET.fromstring(svg)
    text_nodes = document.findall(".//{http://www.w3.org/2000/svg}text")
    weights = {400}
    for node in text_nodes:
        for declaration in node.get("style", "").split(";"):
            if declaration.strip().startswith("font-weight:"):
                weights.add(int(declaration.split(":", 1)[1]))
    font_input = {
        "characters": "".join("".join(node.itertext()) for node in text_nodes),
        "weights": sorted(weights),
    }
    design_root = output.parent.parent
    jobs = design_root.parent / ".scratch" / "penpot-preview-jobs"
    jobs.mkdir(parents=True, exist_ok=True)
    (jobs / f"{output.stem}.svg").write_text(svg, encoding="utf-8")
    renderer = design_root / "render_preview.mjs"
    file_id = json.loads((design_root / "ui-inventory.json").read_text(encoding="utf-8"))["source"]["penpotFileId"]
    job = {
        "spaceId": space_id,
        "fileId": file_id,
        "svg": svg,
        "fontInput": font_input,
        "output": "//wsl.localhost/Ubuntu" + str(output),
    }
    script = renderer.read_text(encoding="utf-8").replace(
        "__PREVIEW_JOB__", json.dumps(job, ensure_ascii=False),
    )
    result = subprocess.run(
        ["ego-browser", "nodejs"], input=script,
        check=False, capture_output=True, text=True, timeout=120,
    )
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    if result.stdout.strip():
        print(result.stdout.strip().splitlines()[-1], flush=True)


def main():
    root = Path(__file__).resolve().parent
    selected = set(sys.argv[1:])
    boards = json.loads((root / "board-index.json").read_text(encoding="utf-8"))["boards"]
    output = root / "previews"
    output.mkdir(exist_ok=True)
    client = McpClient()
    for index, board in enumerate(boards, 1):
        if selected and board["flow"] not in selected:
            continue
        board["client"] = client
        path = output / f"{board['flow']}-{board['flowIndex']:02d}.png"
        capture(board, path, 0)
        print(f"{index}/{len(boards)} {path.name}", flush=True)


if __name__ == "__main__":
    main()
