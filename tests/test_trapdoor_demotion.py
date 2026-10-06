import unittest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot

class TestTrapdoorDemotion(unittest.TestCase):

    @patch('bot.trader.get_live_portfolio')
    @patch('bot.trader.get_current_price')
    @patch('bot.senior_agent.generate_batch_execution_paperwork')
    @patch('bot.trader.close_full_position')
    @patch('bot.minor_league.fetch_leaderboard')
    @patch('bot.league_common.banish_ticker')
    @patch('bot.trader.execute_entry')
    @patch('bot.trader.wait_for_position_fill')
    def test_trapdoor_liquidation_prevents_rebuy(self, mock_wait, mock_execute_entry, mock_banish, mock_fetch_leaderboard, mock_close, mock_paperwork, mock_price, mock_portfolio):
        """
        Validates that if a ticker is liquidated in maintain_portfolio, it is NOT 
        re-bought in execute_swaps (Fill-up scenario), even if it remains highly rated 
        in the Senior_Elo leaderboard.
        """
        # --- PHASE 2.5: PORTFOLIO MAINTENANCE ---
        # The portfolio has TSLA
        mock_portfolio.return_value = ['TSLA']
        mock_price.return_value = 200.0
        
        # The Senior Agent demands TSLA be liquidated (Trapdoor event)
        mock_paperwork.return_value = {
            'TSLA': {'action': 'LIQUIDATE', 'rationale': 'Toxic asset'}
        }
        
        # Alpaca successfully sells it
        mock_close.return_value = "FILLED"
        
        # Execute Phase 2.5
        liquidated_today = bot.maintain_portfolio()
        
        # Verify banish_ticker was called
        mock_banish.assert_called_once_with('TSLA')
        self.assertIn('TSLA', liquidated_today)
        
        # --- PHASE 3: EXECUTE SWAPS ---
        # By the time execute_swaps runs, TSLA is no longer in the portfolio,
        # but let's simulate that the Google Sheets API hasn't propagated the 'N' flag yet 
        # (or just that it returns TSLA with a high Elo).
        mock_fetch_leaderboard.return_value = {
            'TSLA': {'Elo_Rating': 1600.0},
            'AAPL': {'Elo_Rating': 1550.0}
        }
        
        # TSLA is technically unowned now. The portfolio is empty.
        mock_portfolio.return_value = []
        
        # The Senior Agent will provide entry limits for whatever gets selected
        mock_paperwork.return_value = {
            'AAPL': {'action': 'OPEN_NEW', 'entry_price': 150.0}
        }
        
        # Execute Phase 3 with the injected session memory
        bot.execute_swaps(liquidated_today)
        
        # Verify that AAPL was bought, NOT TSLA!
        # Because TSLA should have been explicitly filtered out by liquidated_today.
        mock_execute_entry.assert_called_once()
        called_ticker = mock_execute_entry.call_args[1].get('ticker') or mock_execute_entry.call_args[0][0]
        self.assertEqual(called_ticker, 'AAPL', "TSLA was re-bought! The trapdoor demotion protocol failed.")

if __name__ == '__main__':
    unittest.main()
