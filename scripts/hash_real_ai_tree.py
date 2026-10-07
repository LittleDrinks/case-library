import hashlib
import json
import pathlib
import sys


def files_for(root: pathlib.Path, paths: list[str]) -> list[pathlib.Path]:
    if paths:
        requested = [root / path for path in paths]
        if any(path.is_symlink() for path in requested):
            raise ValueError("invalid hash input")
        files = [path.resolve(strict=True) for path in requested]
        if any(not path.is_relative_to(root) or not path.is_file() for path in files):
            raise ValueError("invalid hash input")
        return files

    return [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and not path.is_symlink()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    ]


def main() -> int:
    root = pathlib.Path(sys.argv[1]).resolve(strict=True)
    paths = sys.argv[2:]
    files = files_for(root, paths)
    if not files:
        raise ValueError("empty hash input")

    rows = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(files)
    }
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    print(hashlib.sha256(encoded).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
