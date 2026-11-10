import sys
if sys.platform == "win32":
    if hasattr(sys.stdout, 'reconfigure'):
        try: sys.stdout.reconfigure(encoding='utf-8')
        except: pass
    if hasattr(sys.stderr, 'reconfigure'):
        try: sys.stderr.reconfigure(encoding='utf-8')
        except: pass

import resend
import config
import math
from datetime import date, datetime
from lib.gvqm_league_common import get_eastern_now
import lib.gvqm_junior_history as junior_history_manager
import lib.gvqm_senior_history as senior_history_manager

def _is_debug_mode() -> bool:
    val = getattr(config, 'DEBUG_MODE', False)
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "t")
    return bool(val)

def _get_subject_prefix() -> str:
    return "[TEST] " if _is_debug_mode() else ""

def format_junior_elo_cell(ticker, junior_board, td_style):
    """
    Formats the Junior Elo table cell for the Major League standings:
      - Active contender: bold score (e.g., <b>1548.2</b>)
      - Dropped/Graduated contender: — (Inactive)
      - Unranked / never in Minor League: —
    """
    if not isinstance(junior_board, dict) or ticker not in junior_board:
        return f'<td style="{td_style} text-align: center; color: #9ca3af;">—</td>'
    
    cand = junior_board[ticker]
    active_status = str(cand.get("Active_Contenders", "N")).strip().upper()
    
    if active_status == "Y":
        elo_val = float(cand.get("Elo_Rating", 1500.0))
        return f'<td style="{td_style} text-align: center; font-weight: bold;">{elo_val:.1f}</td>'
    else:
        return f'<td style="{td_style} text-align: center; color: #6b7280; font-size: 11px;">— (Inactive)</td>'

def send_executive_brief(decision, account_info, portfolio, pending_orders=None, junior_board=None):
    """
    Einstein Simplified Executive Briefing.
    Extracts the clean payload from bot.py and wraps it in a modern HTML template.
    """
    if not getattr(config, 'RESEND_API_KEY', None):
        print("⚠️ [NOTIFIER] Resend API Key missing. Skipping Brief.")
        return

    print("📧 [NOTIFIER] Formatting Executive Briefing (Einstein Simplified)...")
    resend.api_key = config.RESEND_API_KEY
    
    today = get_eastern_now().strftime("%b %d, %Y")
    
    # 1. Extract the Pre-Cleaned Data from bot.py
    actions_text = decision.get("immediate_actions", "No immediate actions today.")
    notes_text = decision.get("ceo_report", "Routine market conditions.")
    standings = decision.get("major_league_standings", [])
    if junior_board is None and isinstance(decision, dict):
        junior_board = decision.get("junior_board")
    
    filled_tickers = [p.symbol for p in portfolio] if portfolio else []
    pending_tickers = [getattr(o, 'symbol', str(o)) for o in pending_orders] if pending_orders else []
    portfolio_tickers = list(set(filled_tickers + pending_tickers))

    # Format text for HTML
    html_actions = actions_text.replace('\n', '<br><br>')
    html_notes = notes_text.replace('\n', '<br><br>')
    
    # Subject Line Logic
    action_count = actions_text.count("SWAP") + actions_text.count("PORTFOLIO")
    base_subject = f"🔔 GVQM Signal: {action_count} Actions | {today}" if action_count > 0 else f"📊 GVQM Daily Brief: {today}"
    subject = f"{_get_subject_prefix()}{base_subject}"

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
    
    if not portfolio and not pending_orders:
        html_content += f"""<tr><td colspan="4" style="padding: 15px; text-align: center; color: #7f8c8d; font-style: italic;">No active positions. Cash is King.</td></tr>"""
    else:
        if portfolio:
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
        if pending_orders:
            for po in pending_orders:
                try:
                    po_sym = getattr(po, 'symbol', str(po))
                    po_qty = getattr(po, 'qty', '-')
                    po_limit = getattr(po, 'limit_price', None)
                    price_str = f"${float(po_limit):,.2f} (Limit)" if po_limit else "Market"
                    html_content += f"""
                    <tr style="border-bottom: 1px solid #eee; background-color: #f9fbf9;">
                        <td style="{TD_STYLE}"><b>{po_sym}</b> <span style="font-size: 10px; color: #27ae60; font-weight: bold;">(Pending Buy)</span></td>
                        <td style="{TD_STYLE} text-align: center;">{po_qty}</td>
                        <td style="{TD_STYLE} text-align: right;">{price_str}</td>
                        <td style="{TD_STYLE} color: #7f8c8d; text-align: right; font-style: italic;">Order Open</td>
                    </tr>
                    """
                except: continue
    html_content += "</tbody></table>"

    # ==========================================================
    # 🏆 SECTION 3: TRIMMED MAJOR LEAGUE STANDINGS
    # ==========================================================
    # Calculate Action Zone thresholds matching Module 6 Front Office Allocation Engine
    total_majors = len(standings)
    major_buy_pct = getattr(config, 'MAJOR_LEAGUE_BUY_PCT', 0.30)
    major_sell_pct = getattr(config, 'MAJOR_LEAGUE_SELL_PCT', 0.30)
    buy_count = max(1, math.ceil(total_majors * major_buy_pct)) if isinstance(major_buy_pct, float) and major_buy_pct <= 1.0 else max(1, int(major_buy_pct))
    sell_count = max(1, math.ceil(total_majors * major_sell_pct)) if isinstance(major_sell_pct, float) and major_sell_pct <= 1.0 else max(1, int(major_sell_pct))
    bottom_start_rank = max(buy_count + 1, total_majors - sell_count + 1)

    html_content += f"""
        <h3 style="color: #8e44ad; border-bottom: 2px solid #8e44ad; padding-bottom: 5px;">🏆 Active Roster vs. Top Challengers</h3>
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px;">
            <thead>
                <tr>
                    <th style="{TH_STYLE} text-align: center; width: 45px;">Rank</th>
                    <th style="{TH_STYLE} text-align: left;">Ticker</th>
                    <th style="{TH_STYLE} text-align: center;">Senior Elo</th>
                    <th style="{TH_STYLE} text-align: center;">Junior Elo</th>
                    <th style="{TH_STYLE} text-align: center;">Status</th>
                    <th style="{TH_STYLE} text-align: center;">Action Zone</th>
                </tr>
            </thead>
            <tbody>
    """

    if not standings:
        html_content += f"""<tr><td colspan="6" style="padding: 15px; text-align: center; color: #7f8c8d; font-style: italic;">No standings data available.</td></tr>"""
    else:
        for rank, item in enumerate(standings, start=1):
            ticker = item[0]
            stats = item[1]
            elo = round(stats.get('Elo_Rating', 1500), 1)
            
            # Highlight your owned stocks vs challengers
            if ticker in filled_tickers:
                status = "🟢 Active"
                bg_color = "#e8f5e9" # Light green
            elif ticker in pending_tickers:
                status = "🟢 Active (Pending)"
                bg_color = "#e8f5e9" # Light green
            else:
                status = "🟡 Challenger"
                bg_color = "#fffde7" # Light yellow

            # Determine Action Zone matching Decoupled Front Office Engine
            if rank <= buy_count:
                zone_label = f"🎯 BUY ZONE (Top {int(major_buy_pct*100)}%)" if isinstance(major_buy_pct, float) and major_buy_pct <= 1.0 else "🎯 BUY ZONE"
                zone_badge = f'<span style="background-color: #d1fae5; color: #065f46; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">{zone_label}</span>'
            elif rank >= bottom_start_rank:
                zone_label = f"🚨 SELL ZONE (Bot {int(major_sell_pct*100)}%)" if isinstance(major_sell_pct, float) and major_sell_pct <= 1.0 else "🚨 SELL ZONE"
                zone_badge = f'<span style="background-color: #fee2e2; color: #991b1b; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">{zone_label}</span>'
            else:
                zone_badge = '<span style="background-color: #f3f4f6; color: #4b5563; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">⏸️ HOLD</span>'
                
            junior_cell = format_junior_elo_cell(ticker, junior_board, TD_STYLE)

            html_content += f"""
            <tr style="background-color: {bg_color}; border-bottom: 1px solid #eee;">
                <td style="{TD_STYLE} text-align: center; font-weight: bold; color: #6b7280;">#{rank}</td>
                <td style="{TD_STYLE} font-weight: bold;">{ticker}</td>
                <td style="{TD_STYLE} text-align: center;">{elo:.1f}</td>
                {junior_cell}
                <td style="{TD_STYLE} text-align: center; font-size: 11px; font-weight: bold;">{status}</td>
                <td style="{TD_STYLE} text-align: center;">{zone_badge}</td>
            </tr>
            """
    html_content += "</tbody></table>"

    # ==========================================================
    # 🔥 SECTION 3.5: MAJOR LEAGUE MOMENTUM
    # ==========================================================
    # Call the newly relocated function
    senior_momentum = senior_history_manager.get_senior_momentum(standings)
    
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
            GVQM Auto-Generated | {get_eastern_now().strftime("%H:%M %Z")}
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


def send_minor_league_scouting_report(daily_matchups, minor_league_standings):
    """Sends the daily Minor League email with Rising Stars."""
    if not getattr(config, 'RESEND_API_KEY', None): return
    resend.api_key = config.RESEND_API_KEY
    
    draft_limit = getattr(config, 'SENIOR_DRAFT_LIMIT', 0.10)
    if isinstance(draft_limit, float) and draft_limit <= 1.0:
        display_pct = round(draft_limit * 1.5, 4)
        display_limit = max(1, math.ceil(round(len(minor_league_standings) * display_pct, 4)))
        pct_val = round(display_pct * 100, 2)
        pct_label = int(pct_val) if pct_val.is_integer() else pct_val
        table_title = f"🏆 Top {display_limit} Heavyweights (Top {pct_label}% Draft Pool & Watchlist)"
    else:
        display_limit = max(1, math.ceil(int(draft_limit) * 1.5))
        table_title = f"🏆 Top {display_limit} Heavyweights (Top {display_limit} Draft Pool & Watchlist)"

    today = get_eastern_now().strftime("%b %d, %Y")
    match_count = len(daily_matchups) if daily_matchups else 0
    
    # Call the newly relocated function
    rising_stars = junior_history_manager.get_rising_stars(minor_league_standings)
    
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

    html_standings = ""
    TD_STYLE = "padding: 10px; border-bottom: 1px solid #eaeaea;"
    for rank, (ticker, data) in enumerate(minor_league_standings[:display_limit], start=1):
        html_standings += f"<tr><td style='{TD_STYLE} color: #6b7280;'>{rank}</td><td style='{TD_STYLE} font-weight: bold;'>{ticker}</td><td style='{TD_STYLE}'>{data.get('Elo_Rating', 1500):.1f}</td></tr>"

    html_battles = ""
    if not daily_matchups:
        html_battles = "<p style='font-size: 13px;'>No Minor League battles occurred today.</p>"
    else:
        for match_string in daily_matchups:
            parts = match_string.split("):", 1)
            header = parts[0].replace("🌱 SCOUT (", "").strip() if len(parts) > 1 else "Matchup"
            body = parts[1].strip() if len(parts) > 1 else match_string

            html_battles += f"""
            <div style="background: #ffffff; padding: 15px; margin-bottom: 12px; border-left: 4px solid #3b82f6; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                <h4 style="margin: 0 0 8px 0; color: #1e3a8a; font-size: 14px;">🥊 {header}</h4>
                <p style="font-size: 13px; margin: 0; color: #4b5563; line-height: 1.6;">{body}</p>
            </div>
            """

    html_content = f"""
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; padding: 20px; background-color: #f3f4f6;">
        <div style="max-width: 600px; margin: auto; background: #ffffff; padding: 25px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
            <h2 style="color: #111827; border-bottom: 2px solid #e5e7eb; padding-bottom: 12px; margin-top: 0;">⚾ Minor League Scouting</h2>
            
            <h3 style="color: #374151; font-size: 15px; margin-top: 20px;">🚀 The Rising Stars (Momentum)</h3>
            {html_stars}

            <h3 style="color: #374151; font-size: 15px; margin-top: 25px;">{table_title}</h3>
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
        "subject": f"{_get_subject_prefix()}⚾ Minor League Scouting: {match_count} Battles Today",
        "html": html_content
    })