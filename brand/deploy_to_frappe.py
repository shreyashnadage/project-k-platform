"""Deploy brand assets to the Frappe custom app.

Run after regenerating CSS from brand.yaml:
    python -m brand.generate_css
    python -m brand.deploy_to_frappe

This copies the generated CSS and logo assets into the Frappe app
directory structure so they can be installed via `bench get-app`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

BRAND_DIR = Path(__file__).parent
FRAPPE_APP_DIR = BRAND_DIR / "frappe_app" / "munimco_brand" / "public"
ASSETS_DIR = BRAND_DIR / "assets"
FRAPPE_CSS_DIR = BRAND_DIR / "frappe"


def deploy() -> None:
    css_dest = FRAPPE_APP_DIR / "css"
    img_dest = FRAPPE_APP_DIR / "images"
    css_dest.mkdir(parents=True, exist_ok=True)
    img_dest.mkdir(parents=True, exist_ok=True)

    # Copy generated CSS
    for css_file in ["desk.css", "portal.css"]:
        src = FRAPPE_CSS_DIR / css_file
        if src.exists():
            shutil.copy2(src, css_dest / css_file)
            print(f"  css: {css_file}")

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

    print(f"\nDone. Frappe app ready at: {FRAPPE_APP_DIR.parent}")
    print("Install on Frappe instance:")
    print("  bench get-app /path/to/munimco_brand")
    print("  bench --site your-site install-app munimco_brand")


if __name__ == "__main__":
    deploy()
