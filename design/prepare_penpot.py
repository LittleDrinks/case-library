import json
from pathlib import Path
from mcp_client import McpClient


TOKENS = [
    {"type": "color", "name": "color.surface", "value": "#F4F6F8"},
    {"type": "color", "name": "color.surfaceInk", "value": "#202B3C"},
    {"type": "color", "name": "color.surfaceMuted", "value": "#626D7A"},
    {"type": "color", "name": "color.surfaceSubtle", "value": "#818A95"},
    {"type": "color", "name": "color.surfaceLine", "value": "#DCE1E7"},
    {"type": "borderRadius", "name": "radius.panel", "value": "9px"},
    {"type": "spacing", "name": "space.44", "value": "44px"},
    {"type": "spacing", "name": "space.56", "value": "56px"},
]


def execute(client, code):
    result = client.call_tool("execute_code", {"code": code})
    text = result["content"][0]["text"]
    if "Tool execution failed" in text:
        raise RuntimeError(text)
    return text


def main():
    client = McpClient()
    token_code = f"""
      const definitions = {json.dumps(TOKENS, ensure_ascii=False)};
      const set = penpot.library.local.tokens.sets.find(item => item.name === 'case-library');
      const added = [];
      for (const definition of definitions) {{
        if (penpotUtils.findTokenByName(definition.name)) continue;
        set.addToken(definition);
        added.push(definition.name);
      }}
      let page = penpotUtils.getPageByName('组件 · 统一设计系统');
      if (!page) page = penpot.createPage();
      page.name = '组件 · 统一设计系统';
      penpot.openPage(page);
      for (let attempt = 0; attempt < 60; attempt += 1) {{
        if (penpot.currentPage?.id === page.id) break;
        await new Promise(resolve => setTimeout(resolve, 250));
      }}
      if (penpot.currentPage.id !== page.id) throw new Error('组件页尚未激活');
      storage.componentPage = penpot.currentPage;
      return {{ added, page: penpot.currentPage.name }};
    """
    print(execute(client, token_code))
    component_code = """
      const ink = '#202B3C';
      const muted = '#626D7A';
      const line = '#DCE1E7';
      const brand = '#BA1C22';
      const surface = '#F4F6F8';
      const existing = name => penpot.library.local.components.find(component => component.name === name);
      function rect(parent, name, x, y, width, height, fill, radius = 0) {
        const shape = penpot.createRectangle();
        shape.name = name;
        shape.x = x; shape.y = y; shape.resize(width, height);
        shape.fills = [{ fillColor: fill, fillOpacity: 1 }];
        if (radius) shape.borderRadius = radius;
        parent.appendChild(shape);
        return shape;
      }
      function text(parent, name, characters, x, y, size, color = ink, weight = 400) {
        const shape = penpot.createText(characters);
        shape.name = name;
        shape.fontFamily = 'Noto Sans SC';
        shape.fontSize = String(size);
        shape.fontWeight = String(weight);
        shape.fills = [{ fillColor: color, fillOpacity: 1 }];
        shape.x = x; shape.y = y;
        shape.growType = 'auto-width';
        parent.appendChild(shape);
        return shape;
      }
      function board(name, x, y, width, height, fill = '#FFFFFF') {
        const shape = penpot.createBoard();
        shape.name = name; shape.x = x; shape.y = y; shape.resize(width, height);
        shape.fills = [{ fillColor: fill, fillOpacity: 1 }];
        return shape;
      }
      let headerComponent = existing('Site Header');
      if (!headerComponent) {
        const header = board('UI / Site Header', 200, 200, 1440, 64);
        rect(header, '底部分隔线', 200, 263, 1440, 1, line);
        const logo = penpot.currentPage.root.children.at(-1);
        logo.resize(150, 44); logo.x = 224; logo.y = 210; logo.name = '上海大学校标';
        header.appendChild(logo);
        text(header, '产品名称', '“强国有我”思政案例库', 392, 220, 15, ink, 600);
        ['首页', '我的案例', '资源检索', '管理后台'].forEach((label, index) => {
          text(header, `导航-${label}`, label, 760 + index * 112, 221, 14, index === 0 ? brand : muted, index === 0 ? 600 : 400);
        });
        text(header, '当前用户', '小李', 1320, 221, 13, muted, 500);
        headerComponent = penpot.library.local.createComponent([header]);
        headerComponent.name = 'UI / Site Header';
      }
      let navigationComponent = existing('Admin Navigation');
      if (!navigationComponent) {
        const navigation = penpot.currentPage.root.children.find(shape => shape.name === 'UI / Admin Navigation')
          || board('UI / Admin Navigation', 200, 360, 230, 440, surface);
        if (!navigation.children.length) {
          text(navigation, '后台标题', '管理后台', 224, 384, 23, ink, 600);
          ['案例管理', '专题与公告', '素材入库', '数据统计', '账号与权限', 'Skill 管理', '标签目录', '平台 AI'].forEach((label, index) => {
            text(navigation, `管理导航-${label}`, label, 232, 440 + index * 44, 14, muted, 500);
          });
        }
        navigationComponent = penpot.library.local.createComponent([navigation]);
        navigationComponent.name = 'Admin Navigation';
      }
      const navigation = navigationComponent.mainInstance();
      navigation.resize(230, 440);
      ['案例管理', '专题与公告', '素材入库', '数据统计', '账号与权限', 'Skill 管理', '标签目录', '平台 AI'].forEach((label, index) => {
        const current = navigation.children.find(shape => shape.name === `管理导航-${label}`);
        if (current) {
          current.x = navigation.x + 32;
          current.y = navigation.y + 80 + index * 44;
          return;
        }
        text(navigation, `管理导航-${label}`, label, navigation.x + 32, navigation.y + 80 + index * 44, 14, muted, 500);
      });
      let searchComponent = existing('Search Field');
      if (!searchComponent) {
        const search = board('UI / Search Field', 520, 360, 620, 60);
        rect(search, '检索背景', 520, 360, 620, 60, '#FFFFFF', 9);
        text(search, '检索提示', '检索案例、知识或教学素材', 548, 379, 14, '#818A95');
        rect(search, '检索按钮背景', 1028, 366, 104, 48, brand, 6);
        text(search, '检索按钮', '检索  →', 1056, 381, 14, '#FFFFFF', 600);
        searchComponent = penpot.library.local.createComponent([search]);
        searchComponent.name = 'Search Field';
      }
      storage.uiComponents = {
        header: headerComponent.name,
        navigation: navigationComponent.name,
        search: searchComponent.name,
      };
      return storage.uiComponents;
    """
    header_exists = json.loads(execute(
        client,
        "return Boolean(penpot.library.local.components.find(component => component.name === 'Site Header'));",
    ))["result"]
    logo_exists = json.loads(execute(
        client,
        "const component = penpot.library.local.components.find(component => component.name === 'Site Header'); return Boolean(component && component.mainInstance().children.some(shape => shape.name === '上海大学校标'));",
    ))["result"]
    if not logo_exists:
        client.call_tool("import_image", {
            "filePath": str(Path(__file__).resolve().parents[1] / "frontend/public/shanghai-university-horizontal-logo.png"),
            "x": 224 if header_exists else 200,
            "y": 210 if header_exists else 200,
            "width": 150 if header_exists else 180,
        })
        if header_exists:
            execute(client, "const logo = penpot.currentPage.root.children.at(-1); logo.name = '上海大学校标'; logo.resize(150, 44); logo.x = 224; logo.y = 210; penpot.library.local.components.find(component => component.name === 'Site Header').mainInstance().appendChild(logo); return logo.id;")
    print(execute(client, component_code))


if __name__ == "__main__":
    main()
