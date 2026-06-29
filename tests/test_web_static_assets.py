from __future__ import annotations

import unittest

from fastapi.testclient import TestClient


class WebStaticAssetTests(unittest.TestCase):
    def test_panel_serves_static_assets_with_real_content_types(self) -> None:
        from doctor_dev_panel.app import app

        client = TestClient(app)

        index = client.get("/")
        self.assertEqual(200, index.status_code)
        self.assertIn("text/html", index.headers.get("content-type", ""))

        app_css = client.get("/assets/css/app.css")
        self.assertEqual(200, app_css.status_code)
        self.assertIn("text/css", app_css.headers.get("content-type", ""))
        self.assertNotIn(b"<!doctype html", app_css.content[:200].lower())

        app_js = client.get("/assets/js/app.js")
        self.assertEqual(200, app_js.status_code)
        content_type = app_js.headers.get("content-type", "")
        self.assertTrue("javascript" in content_type or "ecmascript" in content_type, content_type)
        self.assertNotIn(b"<!doctype html", app_js.content[:200].lower())

        vendor_css = client.get("/assets/vendor/fontawesome/css/all.min.css")
        self.assertEqual(200, vendor_css.status_code)
        self.assertIn("text/css", vendor_css.headers.get("content-type", ""))
        self.assertNotIn(b"<!doctype html", vendor_css.content[:200].lower())

        favicon = client.get("/favicon.ico")
        self.assertEqual(200, favicon.status_code)
        self.assertIn("image/x-icon", favicon.headers.get("content-type", ""))

        missing_asset = client.get("/assets/does-not-exist.css")
        self.assertEqual(404, missing_asset.status_code)


if __name__ == "__main__":
    unittest.main()
