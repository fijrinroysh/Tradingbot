import lib.gvqm_senior_agent as senior_agent
import lib.gvqm_minor_league as minor_league # ✅ NEW: Imported to handle the permanent Scorecard
import random

def calculate_match_elo(winner_elo, loser_elo, k_factor=32):
    """Calculates the Elo shift for a single match."""
    expected_winner = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
    expected_loser = 1 / (1 + 10 ** ((winner_elo - loser_elo) / 400))
    
    new_w = winner_elo + k_factor * (1 - expected_winner)
    new_l = loser_elo + k_factor * (0 - expected_loser)
    return round(new_w, 1), round(new_l, 1)

def run_swiss_league(candidates, num_rounds=3):
    """
    Runs an Intra-Day Swiss League to find today's momentum.
    Also logs the all-time results to the Senior_Elo Scorecard.
    """
    if not candidates:
        return []
    if len(candidates) == 1:
        return candidates
        
    print(f"\n🏆 --- STARTING MAJOR LEAGUE SWISS TOURNAMENT ({len(candidates)} Teams | {num_rounds} Rounds) ---")
    
    # 1. Initialize Daily Elo for all candidates (Resets to 1500 every day to find pure daily momentum)
    for cand in candidates:
        cand['_daily_elo'] = 1500.0
        cand['_wins'] = 0
        cand['_losses'] = 0
        cand['_senior_decision'] = None 
        
														   
    random.shuffle(candidates)

    for round_num in range(1, num_rounds + 1):
        print(f"\n🔔 ROUND {round_num}")
        
																		 
        candidates.sort(key=lambda x: x['_daily_elo'], reverse=True)
        
        for i in range(0, len(candidates), 2):
												   
            if i + 1 >= len(candidates):
                print(f"   🎟️  {candidates[i]['ticker']} gets a Bye!")
                continue
                
            cand_a = candidates[i]
            cand_b = candidates[i+1]
            
            # THE MATCHUP
            result = senior_agent.evaluate_matchup(cand_a, cand_b)
            
            winner_ticker = None
            if result and "final_execution_orders" in result:
                orders = result["final_execution_orders"]
                if orders and len(orders) > 0:
                    winner_ticker = orders[0].get("ticker")
            
            # APPLY ELO MATH & LOG TO PERMANENT SCORECARD
            if winner_ticker == cand_a['ticker']:
                print(f"   🥊 {cand_a['ticker']} def. {cand_b['ticker']}")
                new_w, new_l = calculate_match_elo(cand_a['_daily_elo'], cand_b['_daily_elo'])
                cand_a['_daily_elo'] = new_w
                cand_b['_daily_elo'] = new_l
                cand_a['_wins'] += 1
                cand_b['_losses'] += 1
                cand_a['_senior_decision'] = result 
                
                # ✅ NEW: Save to the permanent Major League Google Sheet
                minor_league.record_match_result("Senior_Elo", cand_a['ticker'], cand_b['ticker'])
                
            elif winner_ticker == cand_b['ticker']:
                print(f"   🥊 {cand_b['ticker']} def. {cand_a['ticker']}")
                new_w, new_l = calculate_match_elo(cand_b['_daily_elo'], cand_a['_daily_elo'])
                cand_b['_daily_elo'] = new_w
                cand_a['_daily_elo'] = new_l
                cand_b['_wins'] += 1
                cand_a['_losses'] += 1
                cand_b['_senior_decision'] = result
                
                # ✅ NEW: Save to the permanent Major League Google Sheet
                minor_league.record_match_result("Senior_Elo", cand_b['ticker'], cand_a['ticker'])
            else:
                print(f"   ⚠️ Match Failed or Tie. No Elo change for {cand_a['ticker']} vs {cand_b['ticker']}.")

    # 3. Final Standings
    candidates.sort(key=lambda x: x['_daily_elo'], reverse=True)
    
    print("\n📊 --- FINAL DAILY STANDINGS ---")
    for rank, cand in enumerate(candidates, 1):
        print(f"   {rank}. {cand['ticker']:<5} | Daily Elo: {cand['_daily_elo']:<6} | {cand['_wins']}W - {cand['_losses']}L")
        
							
    return candidates
	
							   