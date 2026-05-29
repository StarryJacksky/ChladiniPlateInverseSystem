import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import load_config
from src.comsol.server import ensure_comsol_server, is_server_reachable


def main() -> None:
    cfg = load_config("config.yaml")
    print("reachable before:", is_server_reachable("127.0.0.1", 2036))
    ok = ensure_comsol_server(cfg, wait_s=180.0)
    print("ensure_comsol_server ->", ok)
    print("reachable after:", is_server_reachable("127.0.0.1", 2036))


if __name__ == "__main__":
    main()
