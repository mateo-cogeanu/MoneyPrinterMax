import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import voice


class TestLocalKokoroVoice(unittest.TestCase):
    def test_kokoro_voice_dispatches_to_local_provider(self):
        sentinel = object()
        with patch.object(voice, "kokoro_tts", return_value=sentinel) as kokoro_tts:
            result = voice.tts(
                text="A more expressive local voice.",
                voice_name="kokoro:af_heart-Female",
                voice_rate=1.1,
                voice_file="/tmp/kokoro-test.mp3",
            )

        self.assertIs(result, sentinel)
        kokoro_tts.assert_called_once_with(
            text="A more expressive local voice.",
            voice_name="af_heart",
            voice_rate=1.1,
            voice_file="/tmp/kokoro-test.mp3",
        )

    def test_kokoro_asset_download_is_reused(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "model.onnx"
            destination.write_bytes(b"existing-model")
            with patch.object(voice.requests, "get") as get:
                voice._download_kokoro_file(
                    "https://example.invalid/model.onnx", destination
                )

        get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
