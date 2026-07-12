"""Tests for the brand configuration system."""

from __future__ import annotations

from pathlib import Path

import pytest

from brand.brand import BrandConfig, load_brand, reset_brand_cache


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_brand_cache()
    yield
    reset_brand_cache()


class TestBrandConfig:
    def test_load_brand_returns_config(self):
        config = load_brand()
        assert isinstance(config, BrandConfig)

    def test_identity_name_is_set(self):
        config = load_brand()
        assert config.identity.name
        assert len(config.identity.name) > 0

    def test_identity_logo_files_exist(self):
        config = load_brand()
        assert config.identity.logo_full_path().exists()
        assert config.identity.logo_icon_path().exists()

    def test_colors_all_hex(self):
        config = load_brand()
        core_colors = [
            config.colors.cream,
            config.colors.navy,
            config.colors.teal,
            config.colors.saffron,
            config.colors.error,
        ]
        for color in core_colors:
            assert color.startswith("#"), f"{color} is not a hex color"
            assert len(color) == 7, f"{color} is not a 7-char hex"

    def test_chart_series_has_colors(self):
        config = load_brand()
        assert len(config.colors.chart_series) >= 3

    def test_typography_has_fonts(self):
        config = load_brand()
        assert "Plus Jakarta Sans" in config.typography.font_ui
        assert "Mono" in config.typography.font_mono

    def test_shape_radii_are_valid(self):
        config = load_brand()
        for radius in [config.shape.radius_sm, config.shape.radius_md, config.shape.radius_lg]:
            assert radius.endswith("px")

    def test_semantic_colors_map_to_brand(self):
        config = load_brand()
        assert config.colors.semantic_success == config.colors.teal
        assert config.colors.semantic_warning == config.colors.saffron
        assert config.colors.semantic_danger == config.colors.error

    def test_load_is_cached(self):
        a = load_brand()
        b = load_brand()
        assert a is b

    def test_reset_clears_cache(self):
        a = load_brand()
        reset_brand_cache()
        b = load_brand()
        assert a is not b
        assert a.identity.name == b.identity.name


class TestBrandCSSGeneration:
    def test_desk_css_generates(self):
        from brand.generate_css import generate_desk_css

        css = generate_desk_css()
        config = load_brand()
        assert config.colors.navy in css
        assert config.colors.teal in css
        assert config.colors.cream in css
        assert "--primary:" in css
        assert "--bg-color:" in css

    def test_portal_css_generates(self):
        from brand.generate_css import generate_portal_css

        css = generate_portal_css()
        config = load_brand()
        assert config.colors.cream in css

    def test_head_fonts_html_generates(self):
        from brand.generate_css import generate_head_fonts_html

        html = generate_head_fonts_html()
        assert "fonts.googleapis.com" in html
        assert "Plus+Jakarta+Sans" in html

    def test_generated_files_exist(self):
        frappe_dir = Path(__file__).parent.parent / "brand" / "frappe"
        assert (frappe_dir / "desk.css").exists()
        assert (frappe_dir / "portal.css").exists()
        assert (frappe_dir / "head_fonts.html").exists()


class TestBrandAPI:
    def test_brand_endpoint(self):
        from fastapi.testclient import TestClient

        from services.borrower_gateway.app import app

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/brand")
            assert response.status_code == 200
            data = response.json()
            assert "name" in data
            assert "colors" in data
            assert "typography" in data
            assert "shape" in data
            assert data["colors"]["navy"].startswith("#")

    def test_brand_endpoint_has_chart_series(self):
        from fastapi.testclient import TestClient

        from services.borrower_gateway.app import app

        with TestClient(app, raise_server_exceptions=False) as client:
            data = client.get("/brand").json()
            assert len(data["colors"]["chart_series"]) >= 3
