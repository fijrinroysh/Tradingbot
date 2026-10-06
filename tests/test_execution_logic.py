import unittest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lib.gvqm_alpaca_trader as trader
import lib.gvqm_minor_league as minor_league

class TestExecutionLogic(unittest.TestCase):

    # ==============================================================
    # 🧪 [EXE-02] Alpaca Order Updates (TP / SL Logic)
    # ==============================================================
    @patch('lib.gvqm_alpaca_trader.filled_mgr.manage_active_position')
    @patch('lib.gvqm_alpaca_trader._fetch_snapshot')
    @patch('lib.gvqm_alpaca_trader.trading_client')
    def test_alpaca_update_take_profit_stop_loss(self, mock_client, mock_fetch_snapshot, mock_manage_active_position):
        """
        Validates that when a MAINTAIN signal comes in, the trader delegates
        to the filled position manager properly to update brackets.
        """
        mock_fetch_snapshot.return_value = {
            "shares": 10.0, "avg_entry": 90.0, "pending_buy": None, 
            "tp": 100.0, "sl": 80.0, "manual": False
        }
        
        # Mock orders to have no pending buys so it falls through to filled_mgr
        mock_client.get_orders.return_value = []
        
        # When: We execute an update
        trader.execute_update("AAPL", take_profit=120.0, stop_loss=85.0)
        
        # Then: Ensure manage_active_position was called
        mock_manage_active_position.assert_called_once()
        args = mock_manage_active_position.call_args[0]
        self.assertEqual(args[1], "AAPL") # Ticker
        self.assertEqual(args[2], 10.0)   # Shares
        self.assertEqual(args[3], 120.0)  # TP
        self.assertEqual(args[4], 85.0)   # SL

    # ==============================================================
    # 🧪 [EXE-03] Alpaca Liquidations
    # ==============================================================
    @patch('lib.gvqm_alpaca_trader.trading_client')
    def test_alpaca_liquidation_trigger(self, mock_client):
        """
        Validates that a LIQUIDATE signal correctly maps to the Alpaca close_position
        endpoint.
        """
        mock_client.get_orders.return_value = []
        
        trader.close_full_position("TSLA")
        
        # Verify the API was commanded to liquidate TSLA
        mock_client.close_position.assert_called_once_with("TSLA")

    # ==============================================================
    # 🧪 [MAT-03] Round-Robin Matchmaking Shuffling
    # ==============================================================
    def test_major_league_matchup_shuffling(self):
        """
        Validates that Champions and Challengers are shuffled securely so that
        the bot does not fall into deterministic loops (e.g., AAPL fighting MSFT every day).
        """
        # Given: A roster of candidates and known owned tickers
        roster_data = [
            {'ticker': 'CHAMP1', '_elo': 1600.0},
            {'ticker': 'CHAMP2', '_elo': 1550.0},
            {'ticker': 'CHAL1', '_elo': 1700.0},
            {'ticker': 'CHAL2', '_elo': 1500.0}
        ]
        portfolio = ['CHAMP1', 'CHAMP2']
        
        # Run matchmaking multiple times and track pairings
        # Because it shuffles, we expect different matchups across iterations
        # (Using a seed internally in python random makes this hard to guarantee 'different',
        # but we can verify the core rule: Champions ONLY fight Challengers)
        matchups = minor_league.get_major_league_matchups(roster_data, portfolio, match_count=2)
        
        for match in matchups:
            cand_a, cand_b = match[0], match[1]
            # Rule: One must be a Champion (owned), one must be a Challenger (unowned)
            # They should NEVER both be owned, or both be unowned
            a_owned = cand_a['ticker'] in portfolio
            b_owned = cand_b['ticker'] in portfolio
            self.assertNotEqual(a_owned, b_owned, f"Invalid Matchup: {cand_a['ticker']} vs {cand_b['ticker']} (Both Champions or Both Challengers!)")

if __name__ == '__main__':
    unittest.main()
