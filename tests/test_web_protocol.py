import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc")


class WebProtocolTests(unittest.TestCase):
    def test_console_exposes_four_scenario_tabs_and_agentos_dispatch(self):
        html = (ROOT / "demo" / "web" / "index.html").read_text(encoding="utf-8")
        source = (ROOT / "demo" / "web" / "app.js").read_text(encoding="utf-8")

        for scenario in ("normal", "recovery", "intervention", "fastwam"):
            self.assertIn(f'data-scenario="{scenario}"', html)
        self.assertIn('id="task-input"', html)
        self.assertIn('id="dispatch-button"', html)
        self.assertIn('id="evidence-content" hidden', html)
        self.assertNotIn('id="run-select"', html)
        self.assertIn('class="feishu-sidebar"', html)
        self.assertIn('class="feishu-conversation"', html)
        self.assertIn('id="active-instruction"', html)
        self.assertIn("机械臂模型、任务数据与后训练", html)
        self.assertIn("eventAtTime", source)
        self.assertIn("dispatchPlan", source)
        self.assertGreaterEqual(source.count("if (generation !== renderGeneration) return;"), 2)
        self.assertIn("selectedScenario", source)
        self.assertIn("collapseDetails", source)
        self.assertNotIn("select.addEventListener", source)

    def test_console_prefers_declared_presentation_and_retains_raw_fallback(self):
        source = (ROOT / "demo" / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("summary.has_presentation", source)
        self.assertIn("summary.presentation_file", source)
        self.assertIn("summary.video_file", source)
        self.assertNotIn('"/simulation.mp4"', source)

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
        self.assertIn("protocol assertions: 29", result.stdout)


if __name__ == "__main__":
    unittest.main()
