import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Ensure the root directory is accessible so we can import the 'lib' modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lib.gvqm_league_common as league_common

class TestLeagueSync(unittest.TestCase):

    # ==============================================================
    # 🧪 [SYNC-01] & [SYNC-02] Active Contender Exemption & Reset
    # ==============================================================
    @patch('lib.gvqm_league_common.get_client')
    def test_update_active_contenders_flag(self, mock_get_client):
        """
        Validates the 'Smart Bouncer' logic:
        1. Tickers that are active get 'Y'.
        2. Tickers that are inactive get 'N'.
        3. If wipe_inactive_elo is True, inactive tickers also get reset to 1500.
        4. Verifies incremental updates (doesn't push an update if the value is already correct).
        """
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_sheet = MagicMock()
        mock_client.open.return_value = mock_sheet
        mock_worksheet = MagicMock()
        mock_sheet.worksheet.return_value = mock_worksheet
        
        # Given: A mocked Google Sheet state
        mock_worksheet.row_values.return_value = ["Ticker", "Elo_Rating", "Active_Contenders"]
        mock_worksheet.get_all_records.return_value = [
            {"Ticker": "AAPL", "Elo_Rating": 2000.0, "Active_Contenders": "Y"}, # Active, already correct
            {"Ticker": "MSFT", "Elo_Rating": 1800.0, "Active_Contenders": "N"}, # Was inactive, needs to be Y
            {"Ticker": "TSLA", "Elo_Rating": 1600.0, "Active_Contenders": "Y"}, # Was active, needs to be N and reset
            {"Ticker": "COIN", "Elo_Rating": 1500.0, "Active_Contenders": "N"}  # Inactive, already correct and reset
        ]
        
        # When: We run the update with AAPL and MSFT as our "protected/active" tickers
        todays_active = ["AAPL", "MSFT"]
        
        league_common.update_active_contenders_flag("Junior_Elo", todays_active, wipe_inactive_elo=True)
        
        # Then: Check the batch_update payload
        mock_worksheet.batch_update.assert_called_once()
        updates = mock_worksheet.batch_update.call_args[0][0]
        
        # We expect exactly 3 updates:
        # 1. MSFT status to 'Y' (row 3, col C)
        # 2. TSLA status to 'N' (row 4, col C)
        # 3. TSLA Elo to 1500.0 (row 4, col B)
        # AAPL and COIN should not generate updates because they are already in the correct state.
        
        self.assertEqual(len(updates), 3, f"Expected 3 updates, but got {len(updates)}")
        
        # Verify MSFT update
        msft_update = [u for u in updates if u['range'] == 'C3']
        self.assertEqual(msft_update[0]['values'][0][0], 'Y')
        
        # Verify TSLA updates
        tsla_status = [u for u in updates if u['range'] == 'C4']
        tsla_elo = [u for u in updates if u['range'] == 'B4']
        self.assertEqual(tsla_status[0]['values'][0][0], 'N')
        self.assertEqual(tsla_elo[0]['values'][0][0], 1500.0)

if __name__ == '__main__':
    unittest.main()
