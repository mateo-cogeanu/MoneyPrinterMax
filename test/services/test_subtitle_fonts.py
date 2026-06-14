import unittest
from pathlib import Path

from PIL import ImageFont


ROOT_DIR = Path(__file__).parent.parent.parent
FONT_DIR = ROOT_DIR / "resource" / "fonts"
ENGAGING_FONTS = [
    "ArchivoBlack-Regular.ttf",
    "BarlowCondensed-Bold.ttf",
    "Anton-Regular.ttf",
    "PaytoneOne-Regular.ttf",
    "LilitaOne-Regular.ttf",
]


class TestSubtitleFontAssets(unittest.TestCase):
    def test_engaging_subtitle_fonts_are_valid_truetype_files(self):
        for font_name in ENGAGING_FONTS:
            font_path = FONT_DIR / font_name
            self.assertTrue(font_path.is_file(), font_name)
            font = ImageFont.truetype(str(font_path), 60)
            self.assertGreater(font.getlength("Engaging subtitles"), 0)

    def test_engaging_subtitle_fonts_include_license_files(self):
        license_dir = FONT_DIR / "licenses"
        for family in [
            "ArchivoBlack",
            "BarlowCondensed",
            "Anton",
            "PaytoneOne",
            "LilitaOne",
        ]:
            license_path = license_dir / f"{family}-OFL.txt"
            self.assertTrue(license_path.is_file(), family)
            self.assertIn(
                "SIL OPEN FONT LICENSE",
                license_path.read_text(encoding="utf-8").upper(),
            )


if __name__ == "__main__":
    unittest.main()
