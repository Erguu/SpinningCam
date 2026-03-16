
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Ensure project root is in path
sys.path.append(os.getcwd())

# Create the mocks needed BEFORE importing main
mock_pv = MagicMock()
mock_plotter_instance = MagicMock()
mock_plotter_instance.window_size = (1920, 1080)
# Mock add_slider_widget to succeed
mock_slider = MagicMock()
mock_slider.GetRepresentation.return_value.GetValue.return_value = 50
mock_plotter_instance.add_slider_widget.return_value = mock_slider

# Setup the Plotter class mock to return our instance
mock_pv.Plotter.return_value = mock_plotter_instance

# Mock other modules
mock_tk = MagicMock()
mock_logger = MagicMock()

# Apply patches to sys.modules
with patch.dict(sys.modules, {
    'pyvista': mock_pv, 
    'tkinter': mock_tk,
    'logger_config': mock_logger
}):
    from main import SpinningApp

class TestSpinningAppStructure(unittest.TestCase):
    @patch('main.MandrelManager')
    def test_app_instantiation(self, mock_mgr):
        """Test that SpinningApp instantiates without error."""
        print("Testing SpinningApp instantiation...")
        
        try:
            app = SpinningApp()
            
            # Verify plotter is our mock
            self.assertEqual(app.plotter, mock_plotter_instance)
            
            self.assertIsNotNone(app)
            self.assertIsNotNone(app.plotter)
            self.assertIsNotNone(app.ui)
            print("[PASS] App instantiated successfully.")
        except Exception as e:
            self.fail(f"App instantiation failed: {e}")

if __name__ == '__main__':
    unittest.main()
