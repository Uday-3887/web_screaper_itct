from pathlib import Path
import sys


def main() -> int:
    print(f"Python: {sys.version.split()[0]}")
    if sys.version_info[:2] not in {(3, 11), (3, 12)}:
        print("WARNING: Python 3.11 or 3.12 is recommended.")
    try:
        import openpyxl  # noqa: F401
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        print(f"Missing Python package: {exc}")
        return 1
    try:
        with sync_playwright() as playwright:
            executable = Path(playwright.chromium.executable_path)
            if not executable.exists():
                print("Chromium is missing. Run: python -m playwright install chromium")
                return 1
            print(f"Playwright Chromium: {executable}")
    except Exception as exc:
        print(f"Playwright check failed: {exc}")
        return 1
    required_backend_files = [
        Path("dashboard_server.py"), Path("connected_scraper.py"),
        Path("contact_utils.py"), Path("requirements.txt"),
    ]
    missing = [str(path) for path in required_backend_files if not path.is_file()]
    if missing:
        print("Backend files are missing: " + ", ".join(missing))
        return 1
    print("Railway backend: ready")
    print("Installation check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
