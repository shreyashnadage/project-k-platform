"""Deploy brand assets to the back-office (Frappe) custom app.

Run after regenerating CSS/hooks from brand.yaml:
    python -m brand.generate_css
    python -m brand.generate_hooks
    python -m brand.deploy_backoffice_app

This copies the generated CSS and logo assets into the Frappe app
directory structure so they can be installed via `bench get-app`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

BRAND_DIR = Path(__file__).parent
BACKOFFICE_APP_DIR = BRAND_DIR / "backoffice_app" / "munimco_brand" / "public"
ASSETS_DIR = BRAND_DIR / "assets"
GENERATED_CSS_DIR = BRAND_DIR / "generated"


def deploy() -> None:
    css_dest = BACKOFFICE_APP_DIR / "css"
    img_dest = BACKOFFICE_APP_DIR / "images"
    css_dest.mkdir(parents=True, exist_ok=True)
    img_dest.mkdir(parents=True, exist_ok=True)

    # Copy generated CSS
    for css_file in ["desk.css", "portal.css"]:
        src = GENERATED_CSS_DIR / css_file
        if src.exists():
            shutil.copy2(src, css_dest / css_file)
            print(f"  css: {css_file}")

    # Ensure Frappe module subpackage exists
    module_dir = BACKOFFICE_APP_DIR.parent / "munimco_brand"
    module_dir.mkdir(parents=True, exist_ok=True)
    init_file = module_dir / "__init__.py"
    if not init_file.exists():
        init_file.write_text("", encoding="utf-8")

    # Copy logo assets
    asset_map = {
        "munimco_logo_2048.png": "logo.png",
        "munimco_m_icon_cream_512.png": "favicon.png",
        "munimco_logo_linked.svg": "logo.svg",
        "munimco_m_icon_cream.svg": "favicon.svg",
    }
    for src_name, dest_name in asset_map.items():
        src = ASSETS_DIR / src_name
        if src.exists():
            shutil.copy2(src, img_dest / dest_name)
            print(f"  img: {src_name} -> {dest_name}")

    print(f"\nDone. Back-office app ready at: {BACKOFFICE_APP_DIR.parent}")
    print("Install on Frappe instance:")
    print("  bench get-app /path/to/munimco_brand")
    print("  bench --site your-site install-app munimco_brand")


if __name__ == "__main__":
    deploy()
