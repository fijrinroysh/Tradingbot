import unittest
import os
from unittest.mock import patch

class TestConfigOverrides(unittest.TestCase):

    # ==============================================================
    # 🧪 [CFG-01] Environment Precedence
    # ==============================================================
    def test_environment_variable_precedence(self):
        """
        Validates that parameters set in the environment (.env) successfully
        override any hardcoded script defaults in config.py.
        """
        # Patch the environment BEFORE importing config
        with patch.dict(os.environ, {
            'DAILY_SCAN_LIMIT': '42',
            'SCANNER_SMA_MULTIPLIER': '0.75'
        }, clear=True):
            
            # Force reload of config module to simulate initial load under new env
            import importlib
            import config
            importlib.reload(config)
            
            self.assertEqual(config.DAILY_SCAN_LIMIT, 42)
            self.assertEqual(config.SCANNER_SMA_MULTIPLIER, 0.75)

    # ==============================================================
    # 🧪 [CFG-02] Missing Config Fallbacks
    # ==============================================================
    @patch('lib.good_value_quick_money_market_scanner.yf.download')
    @patch('lib.good_value_quick_money_market_scanner.get_sp500_tickers')
    def test_config_missing_fallbacks(self, mock_get_tickers, mock_download):
        """
        Validates that functions correctly use internal defaults (via getattr)
        if config.py is entirely missing a value.
        """
        import config
        import lib.good_value_quick_money_market_scanner as scanner
        import pandas as pd
        
        # Simulate missing SCANNER_SMA_WINDOW from config by deleting it if it exists
        original_window = getattr(config, 'SCANNER_SMA_WINDOW', None)
        if hasattr(config, 'SCANNER_SMA_WINDOW'):
            delattr(config, 'SCANNER_SMA_WINDOW')
            
        try:
            mock_get_tickers.return_value = ["AAPL"]
            # Setup mock data so AAPL qualifies under any normal window
            # The function uses getattr(config, 'SCANNER_SMA_WINDOW', 250)
            mock_df = pd.DataFrame({"AAPL": [100] * 249 + [50]})
            mock_download.return_value = {"Close": mock_df}
            
            # The function should default to 250 if getattr works properly
            distressed = scanner.find_distressed_stocks(sma_multiplier=0.85)
            
            # If it didn't crash and processed 250 items, the default worked
            self.assertIn("AAPL", distressed)
        finally:
            # Restore
            if original_window is not None:
                setattr(config, 'SCANNER_SMA_WINDOW', original_window)

    # ==============================================================
    # 🧪 [CFG-03] Functions Actually Use Config Values
    # ==============================================================
    @patch('lib.good_value_quick_money_market_scanner.yf.download')
    @patch('lib.good_value_quick_money_market_scanner.get_sp500_tickers')
    def test_functions_respect_config_values(self, mock_get_tickers, mock_download):
        """
        Validates that functions genuinely pull and respect the parameters
        set in config.py, proving they don't just ignore it and use hardcoded logic.
        """
        import config
        import lib.good_value_quick_money_market_scanner as scanner
        import pandas as pd
        
        # Override the config directly to an extreme value
        original_multiplier = getattr(config, 'SCANNER_SMA_MULTIPLIER', None)
        setattr(config, 'SCANNER_SMA_MULTIPLIER', 0.50) # 50% discount required
        
        try:
            mock_get_tickers.return_value = ["AAPL", "MSFT"]
            
            # AAPL is at 100, SMA is 100 -> 0% discount
            # MSFT is at 45, SMA is 100 -> 55% discount (Should qualify for 0.50 multiplier)
            
            mock_df = pd.DataFrame({
                "AAPL": [100] * 249 + [100],
                "MSFT": [100] * 249 + [45]
            })
            mock_download.return_value = {"Close": mock_df}
            
            # We call the function WITHOUT passing parameters, forcing it to rely on config
            distressed = scanner.find_distressed_stocks()
            
            # If it used the config (0.50), only MSFT should pass
            self.assertIn("MSFT", distressed)
            self.assertNotIn("AAPL", distressed)
        finally:
            if original_multiplier is not None:
                setattr(config, 'SCANNER_SMA_MULTIPLIER', original_multiplier)

if __name__ == '__main__':
    unittest.main()
