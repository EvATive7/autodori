import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))


with patch("api.BestdoriAPI.get_song_list", return_value={}):
    agent = importlib.import_module("agent")


class FakeClickJob:
    def wait(self):
        return self


class FakeController:
    def __init__(self):
        self.clicks = []

    def post_click(self, x, y):
        self.clicks.append((x, y))
        return FakeClickJob()


class EnsureLiveModeTests(TestCase):
    def _run(self, detail):
        controller = FakeController()
        context = SimpleNamespace(tasker=SimpleNamespace(controller=controller))
        argv = SimpleNamespace(
            reco_detail=SimpleNamespace(
                best_result=SimpleNamespace(detail=detail),
            )
        )
        result = agent.EnsureLiveMode().run(context, argv)
        return result, controller

    def test_clicks_once_when_rehearsal_mode_is_detected(self):
        result, controller = self._run({"switch_required": True})

        self.assertTrue(result.success)
        self.assertEqual(controller.clicks, [(54, 526)])

    def test_does_not_click_when_live_mode_is_already_enabled(self):
        result, controller = self._run({"switch_required": False})

        self.assertTrue(result.success)
        self.assertEqual(controller.clicks, [])
