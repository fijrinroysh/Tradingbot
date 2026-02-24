import resend
import config
import datetime
import re

def send_executive_brief(decision, account_info, portfolio):
    """
    Sends the "Dual-Strategy" Executive Briefing v10.0.
    Now includes a 'Deep Dive' section and the All-Time Major League Scorecard.
    """
    if not getattr(config, 'RESEND_API_KEY', None):
        print("⚠️ [NOTIFIER] Resend API Key missing. Skipping Brief.")
        return

    print("📧 [NOTIFIER] Formatting Executive Briefing (Dual-Strategy Mode)...")
    resend.api_key = config.RESEND_API_KEY
    
    today = datetime.date.today().strftime("%b %d, %Y")
    # This is the list of Dual Objects from the Senior Agent (Includes Mechanical Orders now!)
    orders = decision.get('final_execution_orders', [])
    
    # Filter for Subject Line
    active_moves = [t for t in orders if t.get('action') != 'HOLD']
    subject = f"🔔 GVQM Signal: {len(active_moves)} Actions | {today}"

    # --- STYLES ---
    TH_STYLE = "background-color: #f4f4f4; color: #555; font-size: 10px; text-transform: uppercase; padding: 6px; border: 1px solid #ddd;"
    TD_STYLE = "padding: 8px; font-size: 12px; border: 1px solid #ddd; color: #333;"
    
    # --- HEADER ---
    html_content = f"""
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; color: #333;">
        <div style="background-color: #2c3e50; padding: 15px; border-radius: 6px 6px 0 0;">
            <h2 style="color: #ecf0f1; margin: 0;">🦅 GVQM Executive Brief</h2>
            <p style="color: #bdc3c7; font-size: 12px; margin: 5px 0 0 0;">{today} | Dual-Strategy Protocol</p>
        </div>
        
        <div style="padding: 15px; border: 1px solid #ddd; border-top: none;">
    """

    # ==========================================================
    # ⚡ SECTION 1: IMMEDIATE ACTIONS
    # ==========================================================
    html_content += f"""
        <h3 style="color: #e74c3c; border-bottom: 2px solid #e74c3c; padding-bottom: 5px;">⚡ Immediate Actions Required</h3>
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
            <thead>
                <tr style="{TH_STYLE}">
                    <th style="{TH_STYLE} text-align: left;">Ticker</th>
                    <th style="{TH_STYLE} text-align: center;">Strategy</th>
                    <th style="{TH_STYLE} text-align: center;">Action</th>
                    <th style="{TH_STYLE} text-align: right;">Plan</th>
                </tr>
            </thead>
            <tbody>
    """

    if not active_moves:
        html_content += f"""<tr><td colspan="4" style="padding: 15px; text-align: center; color: #7f8c8d; font-style: italic;">No new actions today. The portfolio is holding steady.</td></tr>"""
    else:
        for order in active_moves:
            ticker = order.get('ticker')
            action = order.get('action')
            rec = order.get('final_recommendation')
            
            # Action Colors
            bg_color = "#e8f8f5" if "OPEN" in action else ("#fdedec" if "CLOSE" in action or "CANCEL" in action else "#fff")
            text_color = "#27ae60" if "OPEN" in action else ("#c0392b" if "CLOSE" in action or "CANCEL" in action else "#333")
            
            # Strategy Details extraction
            if "POSITION" in rec:
                strat_data = order.get('position_trade_analysis', {}).get('execution_plan', {})
            elif "SWING" in rec:
                strat_data = order.get('swing_trade_analysis', {}).get('execution_plan', {})
            else: # Hybrid or default
                strat_data = order.get('position_trade_analysis', {}).get('execution_plan', {})

            tp = strat_data.get('take_profit', 'N/A')
            sl = strat_data.get('stop_loss', 'N/A')

            html_content += f"""
            <tr style="background-color: {bg_color};">
                <td style="{TD_STYLE}"><b>{ticker}</b></td>
                <td style="{TD_STYLE} text-align: center; font-size: 10px;">{rec}</td>
                <td style="{TD_STYLE} text-align: center; color: {text_color}; font-weight: bold;">{action}</td>
                <td style="{TD_STYLE} text-align: right; font-family: monospace;">
                    TP: {tp}<br>SL: {sl}
                </td>
            </tr>
            """
    html_content += "</tbody></table>"

    # ==========================================================
    # 🧠 SECTION 2: ANALYST DEEP DIVE
    # ==========================================================
    # Only show Deep Dive if there are LLM orders (not just mechanical ones)
    llm_orders = [o for o in orders if 'position_trade_analysis' in o]
    
    if llm_orders:
        html_content += f"""
            <h3 style="color: #2980b9; border-bottom: 2px solid #2980b9; padding-bottom: 5px; margin-top: 30px;">🧠 Analyst Deep Dive</h3>
            <p style="font-size: 11px; color: #7f8c8d; margin-bottom: 10px;">Reviewing the logic behind the scores.</p>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                <thead>
                    <tr style="background-color: #f4f4f4;">
                        <th style="{TH_STYLE} width: 10%;">Ticker</th>
                        <th style="{TH_STYLE} width: 45%;">🏛️ Position Thesis (Long Term)</th>
                        <th style="{TH_STYLE} width: 45%;">⚡ Swing Thesis (Momentum)</th>
                    </tr>
                </thead>
                <tbody>
        """

        for order in llm_orders:
            ticker = order.get('ticker')
            rec = order.get('final_recommendation', 'N/A')

            # Extract Position Data
            pos = order.get('position_trade_analysis', {})
            p_score = pos.get('score', 0)
            p_rat = pos.get('rationale', 'N/A')
            p_color = "#27ae60" if p_score >= 70 else ("#e74c3c" if p_score < 40 else "#f39c12")

            # Extract Swing Data
            sw = order.get('swing_trade_analysis', {})
            s_score = sw.get('score', 0)
            s_rat = sw.get('rationale', 'N/A')
            s_color = "#27ae60" if s_score >= 70 else ("#e74c3c" if s_score < 40 else "#f39c12")

            html_content += f"""
            <tr style="border-bottom: 1px solid #eee;">
                <td style="{TD_STYLE} text-align: center; vertical-align: top; background-color: #fafafa;">
                    <b style="font-size: 14px;">{ticker}</b><br>
                    <span style="font-size: 9px; color: #555;">{rec}</span>
                </td>
                <td style="{TD_STYLE} vertical-align: top;">
                    <div style="margin-bottom: 5px;">
                        <span style="background-color: {p_color}; color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold;">Score: {p_score}</span>
                    </div>
                    <div style="font-size: 11px; line-height: 1.4; color: #444;">{p_rat}</div>
                </td>
                <td style="{TD_STYLE} vertical-align: top; border-left: 1px dashed #ddd;">
                    <div style="margin-bottom: 5px;">
                        <span style="background-color: {s_color}; color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold;">Score: {s_score}</span>
                    </div>
                    <div style="font-size: 11px; line-height: 1.4; color: #444;">{s_rat}</div>
                </td>
            </tr>
            """
        html_content += "</tbody></table>"

    # ==========================================================
    # 💼 SECTION 3: PORTFOLIO STATUS
    # ==========================================================
    
    # Calculate Totals
    buying_power = float(account_info.buying_power) if account_info else 0.0
    equity = float(account_info.equity) if account_info else 0.0
    cash_percent = (buying_power / equity * 100) if equity > 0 else 0

    html_content += f"""
        <h3 style="color: #27ae60; border-bottom: 2px solid #27ae60; padding-bottom: 5px; margin-top: 30px;">💼 Portfolio Status</h3>
        <div style="display: flex; justify-content: space-between; background: #ecf0f1; padding: 10px; border-radius: 4px; margin-bottom: 15px;">
            <div><b>Equity:</b> ${equity:,.2f}</div>
            <div><b>Cash:</b> ${buying_power:,.2f} ({cash_percent:.1f}%)</div>
        </div>
        <table style="width: 100%; border-collapse: collapse;">
            <thead>
                <tr style="{TH_STYLE}">
                    <th style="{TH_STYLE} text-align: left;">Ticker</th>
                    <th style="{TH_STYLE} text-align: center;">Qty</th>
                    <th style="{TH_STYLE} text-align: right;">Current $</th>
                    <th style="{TH_STYLE} text-align: right;">P/L ($)</th>
                    <th style="{TH_STYLE} text-align: right;">P/L (%)</th>
                </tr>
            </thead>
            <tbody>
    """
    
    if not portfolio:
        html_content += f"""<tr><td colspan="5" style="padding: 15px; text-align: center; color: #7f8c8d;">No active positions. Cash is King.</td></tr>"""
    
    for p in portfolio:
        try:
            symbol = p.symbol
            qty = float(p.qty)
            current_price = float(p.current_price)
            unrealized_pl = float(p.unrealized_pl)
            pl_percent = float(p.unrealized_plpc) * 100
            
            pl_color = "#27ae60" if unrealized_pl >= 0 else "#c0392b"
            pl_icon = "▲" if unrealized_pl >= 0 else "▼"
            
            html_content += f"""
            <tr style="border-bottom: 1px solid #eee;">
                <td style="{TD_STYLE}"><b>{symbol}</b></td>
                <td style="{TD_STYLE} text-align: center;">{qty}</td>
                <td style="{TD_STYLE} text-align: right;">${current_price:,.2f}</td>
                <td style="{TD_STYLE} color: {pl_color}; font-weight: bold; text-align: right;">{pl_icon} ${unrealized_pl:,.2f}</td>
                <td style="{TD_STYLE} color: {pl_color}; text-align: right;">{pl_percent:+.2f}%</td>
            </tr>
            """
        except: continue
        
    html_content += "</tbody></table>"

    # ==========================================================
    # 🏆 SECTION 4: MAJOR LEAGUE STANDINGS (ALL-TIME ELO)
    # ==========================================================
    leaderboard = decision.get('major_league_standings', [])
    
    html_content += f"""
        <h3 style="color: #8e44ad; border-bottom: 2px solid #8e44ad; padding-bottom: 5px; margin-top: 30px;">🏆 Major League Standings (All-Time)</h3>
        <p style="font-size: 11px; color: #7f8c8d; margin-bottom: 10px;">A holistic view of portfolio hierarchy and newly drafted rookies.</p>
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
            <thead>
                <tr style="{TH_STYLE}">
                    <th style="{TH_STYLE} text-align: center;">Rank</th>
                    <th style="{TH_STYLE} text-align: left;">Ticker</th>
                    <th style="{TH_STYLE} text-align: center;">Elo Rating</th>
                    <th style="{TH_STYLE} text-align: center;">Record (W-L)</th>
                </tr>
            </thead>
            <tbody>
    """

    if not leaderboard:
        html_content += f"""<tr><td colspan="4" style="padding: 15px; text-align: center; color: #7f8c8d; font-style: italic;">No Major League data available yet.</td></tr>"""
    else:
        for index, item in enumerate(leaderboard, 1):
            ticker = item[0]
            stats = item[1]
            elo = stats.get('Elo_Rating', 1500)
            wins = stats.get('Wins', 0)
            losses = stats.get('Losses', 0)
            
            # Highlight Top 3
            row_bg = "#ffffff"
            font_weight = "normal"
            if index == 1: 
                row_bg = "#fffacd" # Gold
                font_weight = "bold"
            elif index == 2: 
                row_bg = "#f8f9fa" # Silver (light grey)
            elif index == 3: 
                row_bg = "#fff0f5" # Bronze (light blush)
                
            html_content += f"""
            <tr style="background-color: {row_bg}; border-bottom: 1px solid #eee;">
                <td style="{TD_STYLE} text-align: center; font-weight: {font_weight};">#{index}</td>
                <td style="{TD_STYLE} font-weight: {font_weight};">{ticker}</td>
                <td style="{TD_STYLE} text-align: center; font-weight: {font_weight};">{elo:.1f}</td>
                <td style="{TD_STYLE} text-align: center; color: #555;">{wins} - {losses}</td>
            </tr>
            """

    html_content += "</tbody></table>"

    # ==========================================================
    # 🏁 FOOTER
    # ==========================================================
    html_content += f"""
        <div style="margin-top: 30px; background-color: #f8f9fa; border: 1px solid #eee; padding: 15px; border-radius: 6px;">
            <h4 style="margin-top: 0; color: #34495e; font-size: 12px; text-transform: uppercase;">🗣️ Senior Manager Notes</h4>
            <p style="font-size: 12px; line-height: 1.5; color: #555; font-style: italic; margin: 0;">
                "{decision.get('ceo_report', 'Session Complete.')}"
            </p>
        </div>
        
        <p style="font-size: 10px; color: #999; text-align: center; margin-top: 20px;">
            GVQM Protocol v10.0 (Elo Integration) | {datetime.datetime.now().strftime("%H:%M EST")}
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