import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc")


class WebProtocolTests(unittest.TestCase):
    @unittest.skipUnless(JSC.is_file(), "macOS JavaScriptCore is not available")
    def test_protocol_rejects_bad_batches_and_reduces_real_events(self):
        result = subprocess.run(
            [str(JSC), str(ROOT / "tests" / "web_protocol_test.js")],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("protocol assertions: 14", result.stdout)


if __name__ == "__main__":
    unittest.main()
