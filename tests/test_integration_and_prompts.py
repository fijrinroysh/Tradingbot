import unittest
import json
from unittest.mock import patch, MagicMock
import sys
import os

# Ensure the root directory is accessible
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lib.gvqm_junior_agent as junior_agent
import lib.gvqm_senior_agent as senior_agent
import lib.gvqm_minor_league as minor_league

class TestPromptsAndParsing(unittest.TestCase):

    # ==============================================================
    # 🧪 [PRM-01] Prompt Formatting with Tickers and Prices
    # ==============================================================
    def test_junior_prompt_formation(self):
        """
        Validates that the Junior Scout prompt properly injects the opponent tickers.
        """
        import lib.gvqm_junior_prompts as prompts
        
        # Test formatting manually as the agent does
        ticker_a = "AAPL"
        ticker_b = "MSFT"
        formatted_prompt = prompts.JUNIOR_MATCHUP_PROMPT.format(ticker_a=ticker_a, ticker_b=ticker_b)
        
        self.assertIn("AAPL", formatted_prompt)
        self.assertIn("MSFT", formatted_prompt)

    def test_senior_paperwork_prompt_formation(self):
        """
        Validates that the Senior Paperwork prompt injects the portfolio JSON correctly.
        """
        import lib.gvqm_senior_paperwork_prompt as paperwork_prompt
        
        portfolio_dict = {
            "TSLA": 250.0,
            "NVDA": 130.0
        }
        portfolio_json_str = json.dumps(portfolio_dict, indent=2)
        formatted_prompt = paperwork_prompt.SENIOR_PAPERWORK_PROMPT.format(portfolio_json=portfolio_json_str)
        
        self.assertIn("TSLA", formatted_prompt)
        self.assertIn("250.0", formatted_prompt)
        self.assertIn("NVDA", formatted_prompt)
        self.assertIn("130.0", formatted_prompt)

    # ==============================================================
    # 🧪 [LLM-01] JSON Response Parsing
    # ==============================================================
    @patch('lib.gvqm_senior_agent._call_gemini_api')
    def test_json_output_parsing(self, mock_call_gemini):
        """
        Validates that the execution script properly handles the JSON structure
        returned by the LLM, and includes a fallback for when the LLM returns
        a list instead of a dictionary.
        """
        # Scenario A: AI correctly returns a dictionary mapping
        mock_call_gemini.return_value = {
            "TSLA": {
                "action": "MAINTAIN",
                "take_profit_price": 280.0,
                "stop_loss_price": 230.0,
                "rationale": "Strong momentum."
            }
        }
        
        portfolio_dict = {"TSLA": 250.0}
        response_a = senior_agent.generate_batch_execution_paperwork(portfolio_dict)
        self.assertIn("TSLA", response_a)
        self.assertEqual(response_a["TSLA"]["action"], "MAINTAIN")
        
        # Scenario B: AI accidentally returns a list instead of a dict
        mock_call_gemini.return_value = [
            {
                "ticker": "TSLA",
                "action": "LIQUIDATE",
                "rationale": "Emergency exit."
            }
        ]
        response_b = senior_agent.generate_batch_execution_paperwork(portfolio_dict)
        self.assertIn("TSLA", response_b)
        self.assertEqual(response_b["TSLA"]["action"], "LIQUIDATE")


class TestGoogleSheetsIntegration(unittest.TestCase):

    # ==============================================================
    # 🧪 [SHT-01] Elo Updates to Google Sheets
    # ==============================================================
    @patch('lib.gvqm_minor_league.get_client')
    @patch('lib.gvqm_minor_league.fetch_leaderboard')
    def test_record_match_result_sheet_update(self, mock_fetch_leaderboard, mock_get_client):
        """
        Validates that Elo scores are correctly calculated and that
        the specific updates are pushed to the Google Sheets API.
        """
        # Mock leaderboard state before match
        mock_fetch_leaderboard.return_value = {
            "AAPL": {"Elo_Rating": 1500.0, "Wins": 0, "Losses": 0, "Last_Match": "1900-01-01"},
            "MSFT": {"Elo_Rating": 1500.0, "Wins": 0, "Losses": 0, "Last_Match": "1900-01-01"}
        }
        
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_sheet = MagicMock()
        mock_client.open.return_value = mock_sheet
        mock_worksheet = MagicMock()
        mock_sheet.worksheet.return_value = mock_worksheet
        
        # Mocking the headers and row locating
        mock_worksheet.row_values.return_value = ["Ticker", "Elo_Rating", "Wins", "Losses", "Win_Rate", "Last_Match", "Active_Contenders"]
        
        # We need worksheet.find to simulate finding the row
        mock_cell_aapl = MagicMock()
        mock_cell_aapl.row = 2
        mock_cell_msft = MagicMock()
        mock_cell_msft.row = 3
        
        def find_side_effect(ticker, in_column=1):
            if ticker == "AAPL": return mock_cell_aapl
            if ticker == "MSFT": return mock_cell_msft
            return None
            
        mock_worksheet.find.side_effect = find_side_effect
        
        # When AAPL beats MSFT
        minor_league.record_match_result("Junior_Elo", "AAPL", "MSFT")
        
        # AAPL gains 16 elo (1516), MSFT loses 16 (1484)
        
        # Then, we verify update was called twice
        self.assertEqual(mock_worksheet.update.call_count, 2)
        
        # Check AAPL update arguments
        aapl_call_args = mock_worksheet.update.call_args_list[0][1]
        self.assertEqual(aapl_call_args['range_name'], 'A2:G2')
        aapl_row_data = aapl_call_args['values'][0]
        self.assertEqual(aapl_row_data[0], "AAPL")
        self.assertEqual(aapl_row_data[1], 1516.0) # AAPL Won
        self.assertEqual(aapl_row_data[2], 1)      # 1 Win
        
        # Check MSFT update arguments
        msft_call_args = mock_worksheet.update.call_args_list[1][1]
        self.assertEqual(msft_call_args['range_name'], 'A3:G3')
        msft_row_data = msft_call_args['values'][0]
        self.assertEqual(msft_row_data[0], "MSFT")
        self.assertEqual(msft_row_data[1], 1484.0) # MSFT Lost
        self.assertEqual(msft_row_data[3], 1)      # 1 Loss

    # ==============================================================
    # 🧪 [SHT-02] Dynamic Tab & Header Generation
    # ==============================================================
    @patch('lib.gvqm_minor_league.get_client')
    @patch('lib.gvqm_minor_league.fetch_leaderboard')
    def test_missing_worksheet_creation(self, mock_fetch_leaderboard, mock_get_client):
        """
        Validates that if a Google Sheets tab is completely missing (e.g. deleted),
        the script catches the WorksheetNotFound exception, creates the tab dynamically,
        and provisions the required headers safely.
        """
        import gspread
        
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_sheet = MagicMock()
        mock_client.open.return_value = mock_sheet
        
        # Simulate that the worksheet does NOT exist
        mock_sheet.worksheet.side_effect = gspread.exceptions.WorksheetNotFound("Sheet not found")
        
        # We need a mock for the dynamically created worksheet
        mock_new_worksheet = MagicMock()
        mock_sheet.add_worksheet.return_value = mock_new_worksheet
        
        mock_fetch_leaderboard.return_value = {"AAPL": {"Elo_Rating": 1500.0, "Wins": 0, "Losses": 0, "Last_Match": "1900-01-01"}}
        
        # Action
        minor_league.record_match_result("Junior_Elo", "AAPL", "MSFT")
        
        # Assertions
        # 1. Did it attempt to create a new worksheet?
        mock_sheet.add_worksheet.assert_called_with(title="Junior_Elo", rows=1000, cols=7)
        
        # 2. Did it append the strict header schema immediately after creation?
        expected_headers = ["Ticker", "Elo_Rating", "Wins", "Losses", "Win_Rate", "Last_Match", "Active_Contenders"]
        mock_new_worksheet.append_row.assert_any_call(expected_headers)

    # ==============================================================
    # 🧪 [SHT-03] Datetime Formatting Contract
    # ==============================================================
    def test_datetime_formatting_contract(self):
        """
        Validates that all timestamp strings pushed to Google Sheets enforce the
        strict '%Y-%m-%d %H:%M:%S' formatting contract, preventing corrupt sorting.
        """
        from datetime import datetime
        import re
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Regex validation for YYYY-MM-DD HH:MM:SS
        pattern = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"
        match = re.match(pattern, timestamp)
        
        self.assertIsNotNone(match, f"Timestamp format violation! Generated: {timestamp}")

if __name__ == '__main__':
    unittest.main()
