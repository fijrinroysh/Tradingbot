import resend
import config
from datetime import date, datetime, timedelta
import lib.gvqm_junior_history as junior_history_manager
import lib.gvqm_senior_history as senior_history_manager

def get_senior_momentum(current_standings):
    """Calculates momentum shifts specifically for the Major League."""
  
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    print("☁️ [NOTIFIER] Loading Major League memory from Google Sheets...")
    history = senior_history_manager.load_senior_history_from_sheets()

    # Save today's snapshot (Rank 1 is the best)
    today_ranks = {ticker: rank for rank, (ticker, data) in enumerate(current_standings, start=1)}
    history[today_str] = today_ranks

    print("☁️ [NOTIFIER] Saving updated Major League memory...")
    senior_history_manager.save_senior_history_to_sheets(history)

    # Look back 3 to 7 days
    target_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    past_ranks = history.get(target_date)
    
    if not past_ranks:
        available_dates = sorted(history.keys())
        if len(available_dates) > 1:
            past_ranks = history[available_dates[0]] 
        else:
            return [] 

    # Calculate Jumps (Only keep positive jumps)
    movers = []
    for ticker, current_rank in today_ranks.items():
        if ticker in past_ranks:
            past_rank = past_ranks[ticker]
            jump = past_rank - current_rank
            if jump > 0:
                movers.append({"ticker": ticker, "jump": jump, "current": current_rank, "past": past_rank})

    # DYNAMIC LIMIT UPDATE
    draft_limit = getattr(config, 'SENIOR_DRAFT_LIMIT', 3)
    return sorted(movers, key=lambda x: x['jump'], reverse=True)[:draft_limit]

def send_executive_brief(decision, account_info, portfolio):
    """
    Einstein Simplified Executive Briefing.
    Extracts the clean payload from bot.py and wraps it in a modern HTML template.
    """
    if not getattr(config, 'RESEND_API_KEY', None):
        print("⚠️ [NOTIFIER] Resend API Key missing. Skipping Brief.")
        return

    print("📧 [NOTIFIER] Formatting Executive Briefing (Einstein Simplified)...")
    resend.api_key = config.RESEND_API_KEY
    
    today = date.today().strftime("%b %d, %Y")
    
    # 1. Extract the Pre-Cleaned Data from bot.py
    actions_text = decision.get("immediate_actions", "No immediate actions today.")
    notes_text = decision.get("ceo_report", "Routine market conditions.")
    standings = decision.get("major_league_standings", [])
    
    portfolio_tickers = [p.symbol for p in portfolio] if portfolio else []

    # Format text for HTML
    html_actions = actions_text.replace('\n', '<br><br>')
    html_notes = notes_text.replace('\n', '<br><br>')
    
    # Subject Line Logic
    action_count = actions_text.count("SWAP") + actions_text.count("PORTFOLIO")
    subject = f"🔔 GVQM Signal: {action_count} Actions | {today}" if action_count > 0 else f"📊 GVQM Daily Brief: {today}"

    # --- STYLES ---
    TH_STYLE = "background-color: #f4f4f4; color: #555; font-size: 11px; text-transform: uppercase; padding: 8px; border: 1px solid #ddd;"
    TD_STYLE = "padding: 10px; font-size: 13px; border: 1px solid #ddd; color: #333;"

    # --- HEADER ---
    html_content = f"""
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; color: #333; line-height: 1.5;">
        <div style="background-color: #2c3e50; padding: 15px; border-radius: 6px 6px 0 0;">
            <h2 style="color: #ecf0f1; margin: 0;">🦅 GVQM Executive Brief</h2>
            <p style="color: #bdc3c7; font-size: 12px; margin: 5px 0 0 0;">{today} | Automated Pipeline</p>
        </div>
        
        <div style="padding: 15px; border: 1px solid #ddd; border-top: none;">
    """

    # ==========================================================
    # ⚡ SECTION 1: IMMEDIATE ACTIONS
    # ==========================================================
    html_content += f"""
        <h3 style="color: #e74c3c; border-bottom: 2px solid #e74c3c; padding-bottom: 5px;">⚡ Immediate Actions Required</h3>
        <div style="background-color: #fdf2f0; padding: 15px; border-left: 4px solid #e74c3c; margin-bottom: 25px; font-size: 13px;">
            {html_actions}
        </div>
    """

    # ==========================================================
    # 💼 SECTION 2: PORTFOLIO STATUS
    # ==========================================================
    buying_power = float(account_info.buying_power) if account_info else 0.0
    equity = float(account_info.equity) if account_info else 0.0
    cash_percent = (buying_power / equity * 100) if equity > 0 else 0

    html_content += f"""
        <h3 style="color: #27ae60; border-bottom: 2px solid #27ae60; padding-bottom: 5px;">💼 Portfolio Status</h3>
        <div style="display: flex; justify-content: space-between; background: #ecf0f1; padding: 10px; border-radius: 4px; margin-bottom: 15px; font-size: 13px;">
            <div><b>Equity:</b> ${equity:,.2f}</div>
            <div><b>Cash:</b> ${buying_power:,.2f} ({cash_percent:.1f}%)</div>
        </div>
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px;">
            <thead>
                <tr>
                    <th style="{TH_STYLE} text-align: left;">Ticker</th>
                    <th style="{TH_STYLE} text-align: center;">Qty</th>
                    <th style="{TH_STYLE} text-align: right;">Current $</th>
                    <th style="{TH_STYLE} text-align: right;">P/L ($)</th>
                </tr>
            </thead>
            <tbody>
    """
    
    if not portfolio:
        html_content += f"""<tr><td colspan="4" style="padding: 15px; text-align: center; color: #7f8c8d; font-style: italic;">No active positions. Cash is King.</td></tr>"""
    else:
        for p in portfolio:
            try:
                symbol = p.symbol
                qty = float(p.qty)
                current_price = float(p.current_price)
                unrealized_pl = float(p.unrealized_pl)
                
                pl_color = "#27ae60" if unrealized_pl >= 0 else "#c0392b"
                pl_icon = "▲" if unrealized_pl >= 0 else "▼"
                
                html_content += f"""
                <tr style="border-bottom: 1px solid #eee;">
                    <td style="{TD_STYLE}"><b>{symbol}</b></td>
                    <td style="{TD_STYLE} text-align: center;">{qty}</td>
                    <td style="{TD_STYLE} text-align: right;">${current_price:,.2f}</td>
                    <td style="{TD_STYLE} color: {pl_color}; font-weight: bold; text-align: right;">{pl_icon} ${unrealized_pl:,.2f}</td>
                </tr>
                """
            except: continue
    html_content += "</tbody></table>"

    # ==========================================================
    # 🏆 SECTION 3: TRIMMED MAJOR LEAGUE STANDINGS
    # ==========================================================
    html_content += f"""
        <h3 style="color: #8e44ad; border-bottom: 2px solid #8e44ad; padding-bottom: 5px;">🏆 Active Roster vs. Top Challengers</h3>
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px;">
            <thead>
                <tr>
                    <th style="{TH_STYLE} text-align: left;">Ticker</th>
                    <th style="{TH_STYLE} text-align: center;">Elo Rating</th>
                    <th style="{TH_STYLE} text-align: center;">Status</th>
                </tr>
            </thead>
            <tbody>
    """

    if not standings:
        html_content += f"""<tr><td colspan="3" style="padding: 15px; text-align: center; color: #7f8c8d; font-style: italic;">No standings data available.</td></tr>"""
    else:
        for item in standings:
            ticker = item[0]
            stats = item[1]
            elo = round(stats.get('Elo_Rating', 1500), 1)
            
            # Highlight your owned stocks vs challengers
            if ticker in portfolio_tickers:
                status = "🟢 Active"
                bg_color = "#e8f5e9" # Light green
            else:
                status = "🟡 Challenger"
                bg_color = "#fffde7" # Light yellow
                
            html_content += f"""
            <tr style="background-color: {bg_color}; border-bottom: 1px solid #eee;">
                <td style="{TD_STYLE} font-weight: bold;">{ticker}</td>
                <td style="{TD_STYLE} text-align: center;">{elo:.1f}</td>
                <td style="{TD_STYLE} text-align: center; font-size: 11px; font-weight: bold;">{status}</td>
            </tr>
            """
    html_content += "</tbody></table>"


    # 2.5: Calculate Major League Momentum
    senior_momentum = get_senior_momentum(standings)
    html_momentum = ""
    if not senior_momentum:
        html_momentum = "<p style='font-size:12px; color: #7f8c8d; font-style: italic;'>Building memory bank... check back in a few days for momentum shifts!</p>"
    else:
        for star in senior_momentum:
            html_momentum += f"""
            <div style="padding: 10px; background: #fff3e0; border-left: 4px solid #f39c12; margin-bottom: 8px; border-radius: 4px;">
                <span style="font-size: 14px;">🔥</span> <b>{star['ticker']}</b> advanced <b>+{star['jump']} spots</b> <span style="color: #6b7280; font-size: 11px;">(Rank {star['past']} ➡️ {star['current']})</span>
            </div>
            """

    # Inject it into the main HTML flow (put this right after the Portfolio table closes)
    html_content += f"""
        <h3 style="color: #f39c12; border-bottom: 2px solid #f39c12; padding-bottom: 5px; margin-top: 25px;">🔥 Major League Momentum</h3>
        <p style="font-size: 12px; color: #6b7280; margin-bottom: 10px;">Tracking the fastest rising Challengers inside the VIP room.</p>
        {html_momentum}
    """
    # ==========================================================
    # 🧠 SECTION 4: SENIOR MANAGER NOTES (THE AI DIARY)
    # ==========================================================
    html_content += f"""
        <div style="background-color: #f4f6f7; border-left: 4px solid #34495e; padding: 15px; border-radius: 4px; margin-top: 10px;">
            <h4 style="margin-top: 0; color: #2c3e50; font-size: 13px; text-transform: uppercase;">🧠 Pipeline Reasoning Log</h4>
            <p style="font-size: 12px; color: #555; margin: 0;">
                {html_notes}
            </p>
        </div>
        
        <p style="font-size: 10px; color: #999; text-align: center; margin-top: 25px;">
            GVQM Auto-Generated | {datetime.now().strftime("%H:%M EST")}
        </p>
        </div>
    </body>
    """

    # --- SEND ---
    try:
        r = resend.Emails.send({
            "from": getattr(config, 'EMAIL_SENDER', "onboarding@resend.dev"),
            "to": getattr(config, 'NOTIFY_EMAIL', "fijrinroysh@gmail.com"), 
            "subject": subject,
            "html": html_content
        })
        print(f"   ✅ [NOTIFIER] Email Sent! ID: {r.get('id')}")
    except Exception as e:
        print(f"   ❌ [NOTIFIER] Failed to send email: {e}")



def get_rising_stars(current_standings):
    """
    Downloads history from Sheets, calculates biggest movers, saves new snapshot.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
   
    
    # 1. Download Memory Bank from Google Sheets
    print("☁️ [NOTIFIER] Loading Minor League memory from Google Sheets...")
    history = junior_history_manager.load_history_from_sheets()

    # 2. Save today's snapshot
    today_ranks = {ticker: rank for rank, (ticker, data) in enumerate(current_standings, start=1)}
    history[today_str] = today_ranks

    # 3. Upload Memory Bank back to Google Sheets
    print("☁️ [NOTIFIER] Saving updated memory to Google Sheets...")
    junior_history_manager.save_history_to_sheets(history)

    # 4. Look back 3 to 7 days
    target_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    past_ranks = history.get(target_date)
    
    if not past_ranks:
        available_dates = sorted(history.keys())
        if len(available_dates) > 1:
            past_ranks = history[available_dates[0]] 
        else:
            return [] # Need more days to calculate!

    # 5. Calculate Jumps
    rising_stars = []
    for ticker, current_rank in today_ranks.items():
        if ticker in past_ranks:
            past_rank = past_ranks[ticker]
            jump = past_rank - current_rank
            if jump > 0:
                rising_stars.append({
                    "ticker": ticker, "jump": jump, "current": current_rank, "past": past_rank
                })

    # DYNAMIC LIMIT UPDATE
    draft_limit = getattr(config, 'SENIOR_DRAFT_LIMIT', 3)
    return sorted(rising_stars, key=lambda x: x['jump'], reverse=True)[:draft_limit]


def send_minor_league_scouting_report(daily_matchups, minor_league_standings):
    """Sends the daily Minor League email with Rising Stars."""
    if not getattr(config, 'RESEND_API_KEY', None): return
    resend.api_key = config.RESEND_API_KEY
    
    # DYNAMIC LIMIT UPDATE
    draft_limit = getattr(config, 'SENIOR_DRAFT_LIMIT', 3)
    
    today = datetime.now().strftime("%b %d, %Y")
    match_count = len(daily_matchups) if daily_matchups else 0
    
    # Get Rising Stars
    rising_stars = get_rising_stars(minor_league_standings)
    
    # Format Rising Stars HTML (Cleaner UI)
    html_stars = ""
    if not rising_stars:
        html_stars = "<p style='font-size:13px; color: #7f8c8d;'><i>Building memory bank... check back tomorrow for momentum shifts!</i></p>"
    else:
        for star in rising_stars:
            html_stars += f"""
            <div style="padding: 12px; background: #f0fdf4; border-left: 4px solid #22c55e; margin-bottom: 8px; border-radius: 4px;">
                <span style="font-size: 16px;">🚀</span> <b>{star['ticker']}</b> jumped <b>+{star['jump']} spots</b> <span style="color: #6b7280; font-size: 12px;">(Rank {star['past']} ➡️ {star['current']})</span>
            </div>
            """

    # Format Heavyweights (DYNAMIC LIMIT APPLIED HERE)
    html_standings = ""
    TD_STYLE = "padding: 10px; border-bottom: 1px solid #eaeaea;"
    for rank, (ticker, data) in enumerate(minor_league_standings[:draft_limit], start=1):
        html_standings += f"<tr><td style='{TD_STYLE} color: #6b7280;'>{rank}</td><td style='{TD_STYLE} font-weight: bold;'>{ticker}</td><td style='{TD_STYLE}'>{data.get('Elo_Rating', 1500):.1f}</td></tr>"

    # Format Battle Rationales (Now accepts the FULL uncut string, formatted beautifully)
    html_battles = ""
    if not daily_matchups:
        html_battles = "<p style='font-size: 13px;'>No Minor League battles occurred today.</p>"
    else:
        for match_string in daily_matchups:
            # Strip out the "🌱 SCOUT (AAA vs BBB):" part to format it cleaner
            parts = match_string.split("):", 1)
            header = parts[0].replace("🌱 SCOUT (", "").strip() if len(parts) > 1 else "Matchup"
            body = parts[1].strip() if len(parts) > 1 else match_string

            html_battles += f"""
            <div style="background: #ffffff; padding: 15px; margin-bottom: 12px; border-left: 4px solid #3b82f6; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                <h4 style="margin: 0 0 8px 0; color: #1e3a8a; font-size: 14px;">🥊 {header}</h4>
                <p style="font-size: 13px; margin: 0; color: #4b5563; line-height: 1.6;">{body}</p>
            </div>
            """

    # DYNAMIC LIMIT APPLIED TO HTML HEADER BELOW
    html_content = f"""
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; padding: 20px; background-color: #f3f4f6;">
        <div style="max-width: 600px; margin: auto; background: #ffffff; padding: 25px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
            <h2 style="color: #111827; border-bottom: 2px solid #e5e7eb; padding-bottom: 12px; margin-top: 0;">⚾ Minor League Scouting</h2>
            
            <h3 style="color: #374151; font-size: 15px; margin-top: 20px;">🚀 The Rising Stars (Momentum)</h3>
            {html_stars}

            <h3 style="color: #374151; font-size: 15px; margin-top: 25px;">🏆 Top {draft_limit} Heavyweights</h3>
            <table style="width: 100%; border-collapse: collapse; text-align: left; margin-bottom: 25px; font-size: 14px;">
                <tr style="background: #f9fafb; color: #6b7280; font-size: 12px; text-transform: uppercase;">
                    <th style="padding: 10px;">Rank</th><th style="padding: 10px;">Ticker</th><th style="padding: 10px;">Elo Score</th>
                </tr>
                {html_standings}
            </table>

            <h3 style="color: #374151; font-size: 15px; border-bottom: 1px solid #e5e7eb; padding-bottom: 8px;">🧠 Scouting Rationales</h3>
            <p style="font-size: 12px; color: #6b7280; margin-bottom: 15px;">Read the AI's full justification for why one stock beat the other based on safety and reward.</p>
            {html_battles}
        </div>
    </body>
    """

    resend.Emails.send({
        "from": getattr(config, 'EMAIL_SENDER', "onboarding@resend.dev"),
        "to": getattr(config, 'NOTIFY_EMAIL', "fijrinroysh@gmail.com"), 
        "subject": f"⚾ Minor League Scouting: {match_count} Battles Today",
        "html": html_content
    })