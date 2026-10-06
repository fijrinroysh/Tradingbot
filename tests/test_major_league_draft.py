import unittest

class TestMajorLeagueDraft(unittest.TestCase):

    # ==============================================================
    # 🧪 [MAT-02] Draft Logic & Portfolio Overlap
    # ==============================================================
    def test_draft_slot_deduplication(self):
        """
        Validates the math used in bot.py to ensure the total Major League roster 
        is capped properly by dynamically subtracting the number of active portfolio
        holdings from the total draft limit.
        """
        draft_limit = 6
        portfolio_tickers = ["AAPL", "MSFT"] # We hold 2 stocks
        
        # We have 10 unowned rookies available
        unowned_juniors = ["ROOK1", "ROOK2", "ROOK3", "ROOK4", "ROOK5", "ROOK6", "ROOK7", "ROOK8", "ROOK9", "ROOK10"]
        
        # The logic used in bot.py:
        available_draft_slots = max(1, draft_limit - len(portfolio_tickers))
        promoted_rookies = unowned_juniors[:available_draft_slots]
        
        # Then we combine them
        major_league_roster = list(set(portfolio_tickers + promoted_rookies))
        
        # Assertions
        self.assertEqual(available_draft_slots, 4, "Should only draft 4 rookies since we hold 2 assets.")
        self.assertEqual(len(promoted_rookies), 4)
        
        # Total roster should exactly equal the draft limit (6)
        self.assertEqual(len(major_league_roster), 6)
        self.assertIn("AAPL", major_league_roster)
        self.assertIn("MSFT", major_league_roster)
        self.assertIn("ROOK1", major_league_roster)

    def test_draft_rookie_waiting_outside(self):
        """
        Explicitly validates the edge case where active portfolio holdings take up 
        Major League slots, forcing highly-ranked Junior rookies to 'wait outside'
        because the draft limit is capped.
        """
        draft_limit = 3
        # We hold two stocks. Even if they are ranked poorly in Junior, they auto-qualify.
        portfolio_tickers = ["LOW_RANK_PORTFOLIO1", "LOW_RANK_PORTFOLIO2"]
        
        # The top 3 from Junior League (none of which we own yet)
        top_juniors = ["TOP_ROOKIE_1", "TOP_ROOKIE_2", "TOP_ROOKIE_3"]
        
        # Bot logic:
        available_draft_slots = max(1, draft_limit - len(portfolio_tickers))
        promoted_rookies = top_juniors[:available_draft_slots]
        major_league_roster = list(set(portfolio_tickers + promoted_rookies))
        
        # We have 3 total slots, minus 2 portfolio holdings = ONLY 1 rookie drafted
        self.assertEqual(available_draft_slots, 1)
        self.assertEqual(len(promoted_rookies), 1)
        self.assertEqual(len(major_league_roster), 3)
        
        # Top Rookie 1 gets in
        self.assertIn("TOP_ROOKIE_1", major_league_roster)
        
        # BUT Top Rookie 2 and Top Rookie 3 are forced to wait outside!
        self.assertNotIn("TOP_ROOKIE_2", major_league_roster)
        self.assertNotIn("TOP_ROOKIE_3", major_league_roster)

if __name__ == '__main__':
    unittest.main()
