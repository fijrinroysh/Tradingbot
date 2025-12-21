import resend
import config
import datetime

def send_executive_brief(decision, account_info, junior_reports, portfolio):
    """
    Sends the "Mirror Protocol" Dashboard v5.3
    Updates:
    - Intelligence Cards now EXCLUDE 'HOLD' actions (Active Only).
    - Senior Decision Matrix retains ALL actions (for audit).
    """
    if not getattr(config, 'RESEND_API_KEY', None):
        print("⚠️ [NOTIFIER] Resend API Key missing. Skipping Brief.")
        return

    print("📧 [NOTIFIER] Formatting Executive Briefing...")
    resend.api_key = config.RESEND_API_KEY
    
    today = datetime.date.today().strftime("%b %d, %Y")
    trades = decision.get('final_execution_orders', [])
    
    subject = f"🔔 GVQM Signal: {len(trades)} Actions | {today}"

    # --- STYLES ---
    TH_STYLE = "background-color: #f4f4f4; color: #555; font-size: 10px; text-transform: uppercase; padding: 6px; border: 1px solid #ddd;"
    TD_STYLE = "padding: 6px; border: 1px solid #ddd; font-size: 11px;"
    
    # CARD STYLES
    CARD_CONTAINER = "border: 1px solid #e0e0e0; border-radius: 8px; margin-bottom: 20px; overflow: hidden; font-family: sans-serif;"
    CARD_HEADER = "padding: 10px 15px; border-bottom: 1px solid #eee;"
    CARD_BODY = "padding: 15px; background-color: #ffffff;"
    
    # IMPROVED PILLAR BOX CSS
    PILLAR_BOX = "background-color: #f9f9f9; padding: 10px; border-radius: 4px; margin-bottom: 8px; font-size: 12px; color: #444; white-space: pre-line; line-height: 1.4;"
    PILLAR_TITLE = "font-weight: bold; color: #555; font-size: 10px; text-transform: uppercase; display: block; margin-bottom: 4px;"
    
    # --- BADGE HELPERS ---
    BADGE_ELITE = "background: #8e44ad; color: #fff; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 10px; border: 1px solid #9b59b6;"
    BADGE_STRONG = "background: #2980b9; color: #fff; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 10px; border: 1px solid #3498db;"
    BADGE_STANDARD = "background: #27ae60; color: #fff; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 10px; border: 1px solid #2ecc71;"

    def format_migration(val_old, val_new, prefix="$"):
        if val_old is None or val_old == val_new or val_old == 'N/A':
            return f"<b>{prefix}{val_new}</b>"
        return f"<span style='color:#999; text-decoration:line-through; font-size:10px;'>{prefix}{val_old}</span> &rarr; <b>{prefix}{val_new}</b>"

    html_content = f"""
    <html>
    <body style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #333; max-width: 600px; margin: auto;">
        
        <div style="background-color: #2c3e50; color: white; padding: 20px; border-radius: 8px 8px 0 0; text-align: center;">
            <h2 style="margin:0; font-size: 20px;">GVQM Strategy Brief</h2>
            <p style="margin:5px 0 0 0; font-size: 12px; opacity: 0.8;">{today}</p>
            <h1 style="margin: 10px 0 0 0; font-size: 32px;">${float(account_info.equity):,.2f}</h1>
            <span style="font-size: 10px; text-transform: uppercase; letter-spacing: 1px;">Total Equity</span>
        </div>

        <div style="background-color: #ecf0f1; padding: 10px; text-align: center; font-size: 12px; border-bottom: 1px solid #bdc3c7;">
            <span style="margin-right: 15px;">💵 Cash: <b>${float(account_info.cash):,.2f}</b></span>
            <span>🚀 BP: <b>${float(account_info.buying_power):,.2f}</b></span>
        </div>
        <br>
    """

    # --- 1. INTELLIGENCE CARDS (Detailed Thesis - ACTIVE ONLY) ---
    # [FIX] Filter out HOLDs for this section
    active_cards = [t for t in trades if t.get('action') != 'HOLD']

    html_content += """
        <h3 style="margin-bottom: 10px; color: #2c3e50; border-bottom: 2px solid #2c3e50; padding-bottom: 5px;">
            🚨 Intelligence Briefing
        </h3>
    """
    
    if not active_cards:
        html_content += f"<p style='text-align: center; color: #999; padding: 20px;'>No active changes required today. Positions held.</p>"
    else:
        for order in active_cards:
            # 1. PARSE DATA
            new_p = order.get('confirmed_params', {})
            old_p = order.get('current_params', {})
            
            action = order.get('action', 'HOLD')
            ticker = order.get('ticker')
            rank = order.get('rank', 10)
            reason = order.get('reason', 'Automated Technical Structure')
            
            # Badge Logic
            try:
                rank_val = int(rank)
                if rank_val <= 2: 
                    rank_style = BADGE_ELITE
                    rank_label = f"🟣 RANK {rank_val}"
                elif rank_val <= 5: 
                    rank_style = BADGE_STRONG
                    rank_label = f"🔵 RANK {rank_val}"
                else: 
                    rank_style = BADGE_STANDARD
                    rank_label = f"🟢 RANK {rank_val}"
            except:
                rank_style = BADGE_STANDARD
                rank_label = "RANK ?"

            # Action Styling
            if action == "OPEN_NEW":
                header_bg = "#eafaf1"
                action_color = "#27ae60"
                action_txt = "🟢 OPEN NEW"
            elif action == "UPDATE_EXISTING":
                header_bg = "#ebf5fb"
                action_color = "#2980b9"
                action_txt = "♻️ UPDATE"
            else:
                header_bg = "#fdedec"
                action_color = "#c0392b"
                action_txt = action

            disp_limit = format_migration(old_p.get('buy_limit'), new_p.get('buy_limit', '-'))
            disp_tp = format_migration(old_p.get('take_profit'), new_p.get('take_profit', '-'))
            disp_sl = format_migration(old_p.get('stop_loss'), new_p.get('stop_loss', '-'))
            
            safe_txt = order.get('justification_safe') or 'N/A'
            bargain_txt = order.get('justification_bargain') or 'N/A'
            rebound_txt = order.get('justification_rebound') or 'N/A'

            # Build Card
            html_content += f"""
            <div style="{CARD_CONTAINER}">
                <div style="{CARD_HEADER} background-color: {header_bg};">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <span style="font-size: 18px; font-weight: bold; color: #333;">{ticker}</span>
                            <span style="{rank_style} margin-left: 6px;">{rank_label}</span>
                            <span style="font-size: 10px; font-weight: bold; color: {action_color}; border: 1px solid {action_color}; padding: 1px 4px; border-radius: 3px; margin-left: 6px;">
                                {action_txt}
                            </span>
                        </div>
                        <div style="text-align: right;">
                            <span style="font-size: 10px; color: #777;">LIMIT PRICE</span><br>
                            <span style="font-size: 14px;">{disp_limit}</span>
                        </div>
                    </div>
                    
                    <div style="margin-top: 8px; padding-top: 6px; border-top: 1px solid rgba(0,0,0,0.05); font-style: italic; font-size: 12px; color: #555; white-space: pre-line;">
                        <b style="color: #333;">💡 Thesis:</b> {reason}
                    </div>
                </div>

                <div style="{CARD_BODY}">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 12px; border-bottom: 1px solid #eee; padding-bottom: 8px;">
                        <div><span style="font-size:11px; color:#7f8c8d;">TARGET:</span> <span style="color:#27ae60;">{disp_tp}</span></div>
                        <div><span style="font-size:11px; color:#7f8c8d;">STOP:</span> <span style="color:#c0392b;">{disp_sl}</span></div>
                    </div>

                    <div style="{PILLAR_BOX} border-left: 3px solid #27ae60;">
                        <span style="{PILLAR_TITLE}">🛡️ Safety Check</span>
                        {safe_txt}
                    </div>
                    <div style="{PILLAR_BOX} border-left: 3px solid #f1c40f;">
                        <span style="{PILLAR_TITLE}">💰 Valuation</span>
                        {bargain_txt}
                    </div>
                    <div style="{PILLAR_BOX} border-left: 3px solid #e67e22;">
                        <span style="{PILLAR_TITLE}">📈 Catalyst</span>
                        {rebound_txt}
                    </div>
                </div>
            </div>
            """

    # --- 2. SENIOR DECISION MATRIX (NEW TABLE - INCLUDES HOLDS) ---
    html_content += """
        <br>
        <h3 style="margin-bottom: 10px; color: #2c3e50; border-bottom: 2px solid #2c3e50; padding-bottom: 5px;">
            📋 Senior Decision Matrix
        </h3>
        <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 11px;">
            <thead>
                <tr style="background-color: #f8f9fa;">
                    <th style="{TH_STYLE}">Rank</th>
                    <th style="{TH_STYLE}">Ticker</th>
                    <th style="{TH_STYLE}">Action</th>
                    <th style="{TH_STYLE}">Limit</th>
                    <th style="{TH_STYLE}">Target</th>
                    <th style="{TH_STYLE}">Stop</th>
                </tr>
            </thead>
            <tbody>
    """
    
    if not trades:
        html_content += f"<tr><td colspan='6' style='{TD_STYLE} text-align: center; color: #999;'>No active decisions generated.</td></tr>"
    else:
        for order in trades:
            ticker = order.get('ticker')
            rank = order.get('rank', 99)
            action = order.get('action', 'HOLD')
            
            p = order.get('confirmed_params', {})
            limit = p.get('buy_limit', 0)
            tp = p.get('take_profit', 0)
            sl = p.get('stop_loss', 0)
            
            # Action Color logic for Table
            act_color = "#333"
            if action == "OPEN_NEW": act_color = "#27ae60"
            elif action == "UPDATE_EXISTING": act_color = "#2980b9"
            elif action == "HOLD": act_color = "#95a5a6"

            html_content += f"""
            <tr>
                <td style="{TD_STYLE}"><b>{rank}</b></td>
                <td style="{TD_STYLE} font-weight:bold;">{ticker}</td>
                <td style="{TD_STYLE} color:{act_color}; font-weight:bold;">{action}</td>
                <td style="{TD_STYLE}">${limit}</td>
                <td style="{TD_STYLE}">${tp}</td>
                <td style="{TD_STYLE}">${sl}</td>
            </tr>
            """
            
    html_content += """
            </tbody>
        </table>
    """

    # --- 3. PORTFOLIO AUDIT SECTION ---
    html_content += """
        <br>
        <h3 style="margin-bottom: 10px; color: #2c3e50; border-bottom: 2px solid #2c3e50; padding-bottom: 5px;">
            📂 Portfolio Audit
        </h3>
        <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 11px;">
            <thead>
                <tr style="background-color: #f8f9fa;">
                    <th style="{TH_STYLE}">Ticker</th>
                    <th style="{TH_STYLE}">Qty</th>
                    <th style="{TH_STYLE}">Entry</th>
                    <th style="{TH_STYLE}">Now</th>
                    <th style="{TH_STYLE}">P/L $</th>
                    <th style="{TH_STYLE}">P/L %</th>
                </tr>
            </thead>
            <tbody>
    """

    if not portfolio:
        html_content += f"<tr><td colspan='6' style='{TD_STYLE} text-align: center; color: #999;'>Portfolio is currently 100% Cash.</td></tr>"
    else:
        for pos in portfolio:
            symbol = pos.symbol
            qty = pos.qty
            avg_entry = float(pos.avg_entry_price)
            current_price = float(pos.current_price)
            unrealized_pl = float(pos.unrealized_pl)
            
            try:
                pl_percent = (unrealized_pl / (avg_entry * float(qty))) * 100
            except (ZeroDivisionError, ValueError):
                pl_percent = 0.0

            pl_color = "#27ae60" if unrealized_pl >= 0 else "#c0392b"
            pl_icon = "▲" if unrealized_pl >= 0 else "▼"

            html_content += f"""
            <tr>
                <td style="{TD_STYLE}"><b>{symbol}</b></td>
                <td style="{TD_STYLE}">{qty}</td>
                <td style="{TD_STYLE}">${avg_entry:,.2f}</td>
                <td style="{TD_STYLE}"><b>${current_price:,.2f}</b></td>
                <td style="{TD_STYLE} color: {pl_color}; font-weight: bold;">{pl_icon} ${unrealized_pl:,.2f}</td>
                <td style="{TD_STYLE} color: {pl_color};">{pl_percent:+.2f}%</td>
            </tr>
            """

    html_content += f"""
            </tbody>
        </table>
        <br>
        <div style="background-color: #f8f9fa; border: 1px solid #eee; padding: 15px; border-radius: 6px;">
            <h4 style="margin-top: 0; color: #34495e; font-size: 12px; text-transform: uppercase;">🗣️ CEO Note</h4>
            <p style="font-size: 12px; line-height: 1.5; color: #555; font-style: italic; margin: 0;">
                "{decision.get('ceo_report', 'No report available.')}"
            </p>
        </div>
        <p style="font-size: 10px; color: #999; text-align: center; margin-top: 20px;">
            GVQM Protocol v5.2 | {datetime.datetime.now().strftime("%H:%M EST")}
        </p>
    </body>
    </html>
    """
    
    try:
        r = resend.Emails.send({
            "from": config.EMAIL_SENDER,
            "to": config.EMAIL_RECIPIENT,
            "subject": subject,
            "html": html_content
        })
        print(f"✅ [NOTIFIER] Email sent successfully. RESEND ID: {r.get('id')}")
    except Exception as e:
        print(f"❌ [NOTIFIER] Failed to send email: {e}")