import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import datetime

# Ensure lib modules can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lib.gvqm_junior_history as junior_history

class TestMomentumLogic(unittest.TestCase):

    # ==============================================================
    # 🧪 [MOM-01] Rising Stars 3-to-7 Day Lookback Logic
    # ==============================================================
    @patch('lib.gvqm_junior_history.save_history_to_sheets')
    @patch('lib.gvqm_junior_history.load_history_from_sheets')
    def test_rising_stars_lookback(self, mock_load, mock_save):
        """
        Validates the momentum rank changes logic.
        Ensures the bot searches history 3 to 7 days back, calculates rank
        improvements properly (past_rank - current_rank > 0), and caps the output.
        """
        today = datetime.datetime.now()
        three_days_ago = (today - datetime.timedelta(days=3)).strftime("%Y-%m-%d")
        four_days_ago = (today - datetime.timedelta(days=4)).strftime("%Y-%m-%d")
        today_str = today.strftime("%Y-%m-%d")
        
        # We simulate that the bot ran 3 days ago and 4 days ago
        # It should prioritize the 3-day-ago data.
        mock_load.return_value = {
            four_days_ago: {
                "AAPL": 10, "MSFT": 5, "TSLA": 20
            },
            three_days_ago: { 
                "AAPL": 8,  # AAPL was rank 8
                "MSFT": 5,  # MSFT was rank 5
                "TSLA": 20  # TSLA was rank 20
            }
        }
        
        # Simulate today's current standings (List of Tuples: (ticker, data))
        current_standings = [
            ("AAPL", {}), # Rank 1 (Jumped from 8 -> 1: +7 jump)
            ("TSLA", {}), # Rank 2 (Jumped from 20 -> 2: +18 jump)
            ("NVDA", {}), # Rank 3 (New entry, no history)
            ("MSFT", {})  # Rank 4 (Jumped from 5 -> 4: +1 jump)
        ]
        
        rising_stars = junior_history.get_rising_stars(current_standings)
        
        # Assertions
        self.assertTrue(len(rising_stars) <= 3)
        
        # TSLA had the biggest jump (+18), so it should be #1
        self.assertEqual(rising_stars[0]['ticker'], "TSLA")
        self.assertEqual(rising_stars[0]['jump'], 18)
        
        # AAPL had the second biggest jump (+7), so it should be #2
        self.assertEqual(rising_stars[1]['ticker'], "AAPL")
        self.assertEqual(rising_stars[1]['jump'], 7)
        
        # MSFT had the smallest jump (+1), so it should be #3
        self.assertEqual(rising_stars[2]['ticker'], "MSFT")
        self.assertEqual(rising_stars[2]['jump'], 1)
        
        # Check that today's snapshot was merged and saved properly
        mock_save.assert_called_once()
        saved_data = mock_save.call_args[0][0]
        self.assertIn(today_str, saved_data)
        self.assertEqual(saved_data[today_str]["AAPL"], 1)

    @patch('lib.gvqm_junior_history.save_history_to_sheets')
    @patch('lib.gvqm_junior_history.load_history_from_sheets')
    def test_rising_stars_no_history(self, mock_load, mock_save):
        """
        Validates that if no history is found within the 3-to-7 day window,
        it safely returns an empty list.
        """
        ten_days_ago = (datetime.datetime.now() - datetime.timedelta(days=10)).strftime("%Y-%m-%d")
        
        # Only history is from 10 days ago (outside the 7-day window)
        mock_load.return_value = {
            ten_days_ago: { "AAPL": 5 }
        }
        
        current_standings = [("AAPL", {})]
        rising_stars = junior_history.get_rising_stars(current_standings)
        
        # Should gracefully return empty because there's no valid baseline
        self.assertEqual(rising_stars, [])

if __name__ == '__main__':
    unittest.main()
