# Case Library architecture tour

`code-map.html` is a standalone, read-only architecture viewer generated from the fixed main revision `7afc5bb9e182b1c61827d6024670002a42937fc6`.

- `flow-app/` contains the React Flow source and generated data/layout inputs.
- `make_data.py` rebuilds data from backend module imports.
- `npm ci --prefix tools/architecture-tour/flow-app` installs dependencies; `npm run build --prefix tools/architecture-tour/flow-app` rebuilds the standalone HTML.
- The persistent copy is outside `/tmp`; `/tmp` is only a disposable handoff.
