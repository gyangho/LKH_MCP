"""Native graceful shutdown and Pixel Pig palette regression tests."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import native_shutdown
try:
    from PIL import Image
except ImportError:
    Image = None


class NativeShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_native_mode_can_arm_shutdown(self):
        event = asyncio.Event()
        with patch.dict("os.environ", {"LKH_NATIVE_MODE": "0"}):
            with self.assertRaises(RuntimeError):
                native_shutdown.arm(event)
        with patch.dict("os.environ", {"LKH_NATIVE_MODE": "1"}):
            native_shutdown.arm(event)
            native_shutdown.schedule_shutdown(0.2)
            await asyncio.wait_for(event.wait(), 1.0)
        with patch.dict("os.environ", {"LKH_NATIVE_MODE": "0"}):
            with self.assertRaises(RuntimeError):
                native_shutdown.schedule_shutdown()


@unittest.skipUnless(Image is not None, "Pillow is a Windows packaging dependency")
class PixelPigTests(unittest.TestCase):
    def test_original_color_and_true_gray_server_only_state(self):
        from scripts.generate_icon import generate
        with tempfile.TemporaryDirectory() as td:
            generate(Path(td))
            with (Image.open(Path(td) / "pig-online.png") as online,
                  Image.open(Path(td) / "pig-offline.png") as offline,
                  Image.open(Path(td) / "pig-unknown.png") as unknown):
                self.assertEqual(online.size, offline.size)
                self.assertEqual(online.size, unknown.size)
                a = list(online.convert("RGBA").getdata())
                b = list(offline.convert("RGBA").getdata())
                c = list(unknown.convert("RGBA").getdata())
                self.assertEqual([x[3] for x in a], [x[3] for x in b])
                self.assertEqual([x[3] for x in a], [x[3] for x in c])
                self.assertTrue(all(x[0] == x[1] == x[2] for x in b))
                self.assertTrue(any(x[0] != x[1] for x in a if x[3] > 0))


if __name__ == "__main__":
    unittest.main()
