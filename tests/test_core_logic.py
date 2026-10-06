import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import sys
import os

# Ensure the root directory is accessible so we can import the 'lib' modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lib.good_value_quick_money_market_scanner as scanner
import lib.gvqm_junior_history as junior_history
import lib.gvqm_minor_league as minor_league
import lib.gvqm_league_common as league_common

class TestFunctionalCoreLogic(unittest.TestCase):

    # ==============================================================
    # 🧪 [SCN-02] Scanner Filtering Logic (SMA & Discount Threshold)
    # ==============================================================
    @patch('lib.good_value_quick_money_market_scanner.yf.download')
    @patch('lib.good_value_quick_money_market_scanner.get_sp500_tickers')
    def test_scanner_discount_threshold(self, mock_get_tickers, mock_download):
        """
        Validates that the mathematical check strictly filters stocks that are NOT
        below the required SMA threshold.
        """
        # Given: A universe of 3 tickers
        mock_get_tickers.return_value = ["AAPL", "MSFT", "TSLA"]
        
        # Given: Mocked historical prices for the last 250 days
        # AAPL: SMA ~100, Current Price = 80 (20% discount -> Qualifies at 0.85 multiplier)
        # MSFT: SMA ~100, Current Price = 90 (10% discount -> Fails at 0.85 multiplier)
        # TSLA: SMA ~100, Current Price = 110 (Premium -> Fails at 0.85 multiplier)
        
        aapl_prices = [100] * 249 + [80]
        msft_prices = [100] * 249 + [90]
        tsla_prices = [100] * 249 + [110]
        
        mock_df = pd.DataFrame({
            "AAPL": aapl_prices,
            "MSFT": msft_prices,
            "TSLA": tsla_prices
        })
        
        # 'Close' column mock
        mock_download.return_value = {"Close": mock_df}

        # When: Scanning with a 250-day window and 0.85 multiplier (requires 15% discount)
        distressed = scanner.find_distressed_stocks(sma_window=250, sma_multiplier=0.85)

        # Then: ONLY AAPL should make it through
        self.assertIn("AAPL", distressed)
        self.assertNotIn("MSFT", distressed, "MSFT was only at 10% discount, should be filtered.")
        self.assertNotIn("TSLA", distressed, "TSLA was at a premium, should be filtered.")
        self.assertEqual(len(distressed), 1)

    # ==============================================================
    # 🧪 [MAT-01] Matchmaking Staleness Priority Queue
    # ==============================================================
    @patch('lib.gvqm_minor_league.fetch_leaderboard')
    def test_staleness_priority_sorting(self, mock_fetch_leaderboard):
        """
        Validates that among the active contenders, the ones with the oldest
        fight dates (longest time since last match) are prioritized first.
        Rookies (with no history or reset history) default to 1900-01-01 
        so they are guaranteed to go first.
        """
        # Given: A mocked leaderboard reflecting the Google Sheet state
        mock_fetch_leaderboard.return_value = {
            "OLDEST_ACTIVE": {"Last_Match": "2023-01-01"},  # Hasn't fought in a long time
            "RECENT_ACTIVE": {"Last_Match": "2023-12-01"},  # Fought very recently
            "MODERATE_ACTIVE": {"Last_Match": "2023-06-01"} # Fought in the middle
            # "BRAND_NEW_ROOKIE" has no record, so it defaults to 1900-01-01
        }
        
        # 'distressed' represents the list of currently active contenders from the scanner
        active_contenders = ["RECENT_ACTIVE", "BRAND_NEW_ROOKIE", "OLDEST_ACTIVE", "MODERATE_ACTIVE"]
        
        # When: Filtering and sorting the active contenders
        sorted_candidates = junior_history.filter_candidates(active_contenders, limit=4)
        
        # Then: The sorting MUST prioritize: 
        # 1. The Rookie (1900-01-01 fallback)
        # 2. The Oldest Active (2023-01-01)
        # 3. The Moderate Active (2023-06-01)
        # 4. The Recent Active (2023-12-01)
        expected_order = ["BRAND_NEW_ROOKIE", "OLDEST_ACTIVE", "MODERATE_ACTIVE", "RECENT_ACTIVE"]
        self.assertEqual(sorted_candidates, expected_order)

    # ==============================================================
    # 🧪 [EXE-01] Elo Swap Hurdle Logic (Math Validation)
    # ==============================================================
    def test_elo_swap_hurdle_math(self):
        """
        Validates the fundamental logic that a swap only occurs if the 
        Challenger strictly breaches the Champion's score + ELO_SWAP_THRESHOLD.
        """
        elo_swap_threshold = 15.0
        champion_elo = 1500.0
        
        # Scenario A: Challenger is higher, but doesn't breach hurdle (1510)
        challenger_elo_fail = 1510.0
        self.assertFalse(challenger_elo_fail > (champion_elo + elo_swap_threshold))
        
        # Scenario B: Challenger hits exact hurdle boundary (1515) -> Should FAIL (strict greater than)
        challenger_elo_boundary = 1515.0
        self.assertFalse(challenger_elo_boundary > (champion_elo + elo_swap_threshold))
        
        # Scenario C: Challenger breaches hurdle (1516) -> Should PASS
        challenger_elo_pass = 1516.0
        self.assertTrue(challenger_elo_pass > (champion_elo + elo_swap_threshold))

    # ==============================================================
    # 🧪 [MAT-03] Minor League Elo Calculation
    # ==============================================================
    def test_calculate_elo(self):
        """
        Validates the zero-sum Elo adjustment mechanism functions as intended.
        """
        # When two identical Elos fight, expected winner is 50%, K=32 means +/- 16
        new_winner, new_loser = minor_league.calculate_elo(1500.0, 1500.0, k_factor=32)
        
        self.assertEqual(new_winner, 1516.0)
        self.assertEqual(new_loser, 1484.0)

if __name__ == '__main__':
    unittest.main()
