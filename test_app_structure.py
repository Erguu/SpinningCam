# -*- coding: utf-8 -*-
"""Headless smoke test: SpinningApp can be constructed at all.

This is the cheapest test in the suite and it covers the widest surface. The
constructor loads settings, builds the plotter scene, creates the path generator
and runs a first `update_scene`, so an import-time break or a constructor-order
mistake anywhere in that chain shows up here before it shows up as a program
that will not start.

WHAT WAS STALE (fixed 2026-09-10)

It had been failing at HEAD for months with

    TypeError: '<' not supported between instances of 'MagicMock' and 'int'

`_update_grid_dynamic` (main.py:359) asks every visible actor for its bounds and
compares them with numbers. A bare `MagicMock` plotter returns a MagicMock from
`add_mesh`, whose `GetBounds()` is another MagicMock — so the mock, not the code,
was what broke. The plotter mock now hands back actors with real numeric bounds.

It also asserted `app.ui is not None`, which the constructor has never satisfied:
`SpinningApp.__init__` sets `self.ui = None` (main.py:79) and the Tk window
attaches itself afterwards. That assertion is now inverted, so the test states
what the design actually is instead of what someone assumed.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def _make_actor():
    """A stand-in vtk actor with the two methods the scene code calls on it.

    Numeric bounds are the entire point: they are what `_update_grid_dynamic`
    compares against its defaults.
    """
    actor = MagicMock()
    actor.GetBounds.return_value = (-50.0, 50.0, -50.0, 50.0, 0.0, 200.0)
    actor.GetVisibility.return_value = True
    return actor


mock_pv = MagicMock()
mock_plotter_instance = MagicMock()
mock_plotter_instance.window_size = (1920, 1080)
mock_plotter_instance.add_mesh.side_effect = lambda *a, **k: _make_actor()
mock_plotter_instance.add_points.side_effect = lambda *a, **k: _make_actor()
mock_plotter_instance.add_lines.side_effect = lambda *a, **k: _make_actor()

mock_slider = MagicMock()
mock_slider.GetRepresentation.return_value.GetValue.return_value = 50
mock_plotter_instance.add_slider_widget.return_value = mock_slider

mock_pv.Plotter.return_value = mock_plotter_instance

with patch.dict(sys.modules, {
    'pyvista': mock_pv,
    'tkinter': MagicMock(),
    'logger_config': MagicMock(),
}):
    from main import SpinningApp


class TestSpinningAppStructure(unittest.TestCase):

    @patch('main.MandrelManager')
    def test_app_instantiation(self, mock_mgr):
        """The constructor completes and leaves the core objects in place."""
        app = SpinningApp()

        self.assertEqual(app.plotter, mock_plotter_instance)
        self.assertIsNotNone(app.path_gen)
        self.assertIsNotNone(app.mandrel_mgr)
        self.assertIsInstance(app.params, dict)
        self.assertTrue(app.params, "settings loaded empty")

    @patch('main.MandrelManager')
    def test_ui_is_attached_later_not_by_the_constructor(self, mock_mgr):
        """Pins the actual contract (main.py:79).

        The Tk window sets `app.ui` on itself after constructing the app. Code
        that runs during __init__ therefore cannot reach the UI, which is why
        `update_scene` has to work with no window attached.
        """
        app = SpinningApp()
        self.assertIsNone(app.ui)

    @patch('main.MandrelManager')
    def test_first_scene_update_ran(self, mock_mgr):
        """The constructor ends with update_scene('all'), so by the time it
        returns there is something in the scene. A plotter that was never asked
        to draw means the first frame is blank until the user touches
        something."""
        app = SpinningApp()
        self.assertTrue(mock_plotter_instance.add_mesh.called
                        or mock_plotter_instance.add_points.called,
                        "nothing was ever added to the scene")


if __name__ == '__main__':
    unittest.main()
