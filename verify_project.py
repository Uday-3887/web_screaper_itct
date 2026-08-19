import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(command, cwd, env=None):
    print("Running:", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True, env=env)


def main() -> int:
    required = [
        BACKEND / "Dockerfile", BACKEND / "railway.toml", BACKEND / "dashboard_server.py",
        BACKEND / "connected_scraper.py", BACKEND / "requirements.txt",
        FRONTEND / "index.html", FRONTEND / "styles.css", FRONTEND / "app.js",
        FRONTEND / "config.js", FRONTEND / "vercel.json", ROOT / "DEPLOYMENT_GUIDE.md",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    require(not missing, "Missing required files: " + ", ".join(missing))

    with (FRONTEND / "vercel.json").open(encoding="utf-8") as handle:
        json.load(handle)
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    require('id="maxResults"' in html and 'max="2000"' in html, "Frontend maximum result limit is not 2000.")
    require("config.js" in html and html.index("config.js") < html.index("app.js"), "config.js must load before app.js.")

    forbidden = [ROOT / ".venv", BACKEND / ".venv", BACKEND / "browser_profile", BACKEND / "dashboard_data", BACKEND / "output"]
    present_forbidden = [str(path.relative_to(ROOT)) for path in forbidden if path.exists()]
    require(
        not present_forbidden,
        "Generated or sensitive local directories were included: " + ", ".join(present_forbidden)
    )

    syntax_check = (
        "from pathlib import Path; "
        "files=['dashboard_server.py','connected_scraper.py','contact_utils.py']; "
        "[compile(Path(f).read_text(encoding='utf-8'), f, 'exec') for f in files]"
    )
    run([sys.executable, "-c", syntax_check], BACKEND)
    with tempfile.TemporaryDirectory() as directory:
        test_env = os.environ.copy()
        test_env.update({
            "PYTHONDONTWRITEBYTECODE": "1",
            "ITCYBER_DATA_DIR": str(Path(directory) / "data"),
            "ITCYBER_OUTPUT_DIR": str(Path(directory) / "output"),
        })
        run(
            [sys.executable, "-m", "unittest", "-v", "test_dashboard.py", "test_utils.py", "test_api_integration.py"],
            BACKEND,
            env=test_env,
        )
    if shutil.which("node"):
        run(["node", "--check", "app.js"], FRONTEND)
        run(["node", "--check", "config.js"], FRONTEND)
    else:
        print("Node.js not available; JavaScript syntax checks skipped.")
    print("All project verification checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
