import resend
import config
import datetime

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
    
    today = datetime.date.today().strftime("%b %d, %Y")
    
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
            GVQM Auto-Generated | {datetime.datetime.now().strftime("%H:%M EST")}
        </p>
        </div>
    </body>
    """

    # --- SEND ---
    try:
        r = resend.Emails.send({
            "from": "onboarding@resend.dev",
            "to": getattr(config, 'NOTIFY_EMAIL', "fijrinroysh@gmail.com"), 
            "subject": subject,
            "html": html_content
        })
        print(f"   ✅ [NOTIFIER] Email Sent! ID: {r.get('id')}")
    except Exception as e:
        print(f"   ❌ [NOTIFIER] Failed to send email: {e}")


import lib.gvqm_junior_history as history_manager
from datetime import datetime, timedelta

def get_rising_stars(current_standings):
    """
    Downloads history from Drive, calculates biggest movers, saves new snapshot to Drive.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # 1. Download Memory Bank from Google Drive
    print("☁️ [NOTIFIER] Loading Minor League history from Google Drive...")
    history = history_manager.load_history_from_drive()

    # 2. Save today's snapshot
    today_ranks = {ticker: rank for rank, (ticker, data) in enumerate(current_standings, start=1)}
    history[today_str] = today_ranks

    # 3. Upload Memory Bank back to Google Drive
    print("☁️ [NOTIFIER] Saving updated history to Google Drive...")
    history_manager.save_history_to_drive(history)

    # 4. Look back 3 to 7 days
    target_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    past_ranks = history.get(target_date)
    
    if not past_ranks:
        available_dates = sorted(history.keys())
        if len(available_dates) > 1:
            # Use the oldest date we have if 3 days doesn't exist yet
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

    # Return top 3 jumpers
    return sorted(rising_stars, key=lambda x: x['jump'], reverse=True)[:3]


def send_minor_league_scouting_report(daily_matchups, minor_league_standings):
    """Sends the daily Minor League email with Rising Stars."""
    if not getattr(config, 'RESEND_API_KEY', None): return
    resend.api_key = config.RESEND_API_KEY
    
    today = datetime.now().strftime("%b %d, %Y")
    
    # Get Rising Stars
    rising_stars = get_rising_stars(minor_league_standings)
    
    # Format Rising Stars HTML
    html_stars = ""
    if not rising_stars:
        html_stars = "<p style='font-size:13px;'><i>Building memory bank... check back tomorrow for Rising Stars!</i></p>"
    else:
        for star in rising_stars:
            html_stars += f"""
            <div style="padding: 10px; background: #e8f5e9; border-left: 4px solid #2ecc71; margin-bottom: 10px;">
                <b>🚀 {star['ticker']}</b> jumped <b>+{star['jump']} spots</b> (Rank {star['past']} ➡️ {star['current']})
            </div>
            """

    # Format Heavyweights (Top 5)
    html_standings = ""
    TD_STYLE = "padding: 8px; border-bottom: 1px solid #ddd;"
    for rank, (ticker, data) in enumerate(minor_league_standings[:5], start=1):
        html_standings += f"<tr><td style='{TD_STYLE}'>{rank}</td><td style='{TD_STYLE}'><b>{ticker}</b></td><td style='{TD_STYLE}'>{data.get('Elo_Rating', 1500):.1f}</td></tr>"

    # Format Battle Rationales
    html_battles = ""
    for match in daily_matchups:
        html_battles += f"""
        <div style="background: #f9f9f9; padding: 15px; margin-bottom: 10px; border-radius: 5px;">
            <h4 style="margin: 0 0 5px 0;">🥊 {match.get('winner', 'N/A')} def. {match.get('loser', 'N/A')}</h4>
            <p style="font-size: 13px; margin: 0; color: #555;">{match.get('rationale', '')}</p>
        </div>
        """

    html_content = f"""
    <body style="font-family: Arial; padding: 20px; background-color: #f4f4f4;">
        <div style="max-width: 600px; margin: auto; background: #fff; padding: 20px; border-radius: 8px;">
            <h2 style="color: #2c3e50; border-bottom: 2px solid #2980b9; padding-bottom: 10px;">⚾ Minor League Scouting Report</h2>
            
            <h3 style="color: #2980b9;">🚀 The Rising Stars</h3>
            {html_stars}

            <h3 style="color: #2980b9;">🏆 Top 5 Heavyweights</h3>
            <table style="width: 100%; border-collapse: collapse; text-align: center; margin-bottom: 20px;">
                <tr style="background: #ecf0f1;"><th>Rank</th><th>Ticker</th><th>Elo</th></tr>
                {html_standings}
            </table>

            <h3 style="color: #2980b9;">📊 Matchup Learning Lab</h3>
            {html_battles}
        </div>
    </body>
    """

    resend.Emails.send({
        "from": getattr(config, 'RESEND_FROM_EMAIL', "onboarding@resend.dev"),
        "to": [config.USER_EMAIL],
        "subject": "⚾ Minor League Scouting Report",
        "html": html_content
    })