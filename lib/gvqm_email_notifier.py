import resend
import config
import datetime
import re

def send_executive_brief(decision, account_info, portfolio):
    """
    Sends the "Dual-Strategy" Executive Briefing v8.0.
    Now handles Position vs Swing logic dynamically.
    """
    if not getattr(config, 'RESEND_API_KEY', None):
        print("⚠️ [NOTIFIER] Resend API Key missing. Skipping Brief.")
        return

    print("📧 [NOTIFIER] Formatting Executive Briefing (Dual-Strategy Mode)...")
    resend.api_key = config.RESEND_API_KEY
    
    today = datetime.date.today().strftime("%b %d, %Y")
    # This is the list of Dual Objects from the Senior Agent
    orders = decision.get('final_execution_orders', [])
    
    # Filter for Subject Line
    active_moves = [t for t in orders if t.get('action') != 'HOLD']
    subject = f"🔔 GVQM Signal: {len(active_moves)} Actions | {today}"

    # --- STYLES ---
    TH_STYLE = "background-color: #f4f4f4; color: #555; font-size: 10px; text-transform: uppercase; padding: 6px; border: 1px solid #ddd;"
    TD_STYLE = "padding: 6px; font-size: 12px; border: 1px solid #ddd; color: #333;"
    
    # --- BUILD HTML ---
    html_content = f"""
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background-color: #2c3e50; color: white; padding: 15px; border-radius: 6px 6px 0 0;">
            <h2 style="margin: 0;">🏛️ GVQM Executive Brief</h2>
            <p style="margin: 5px 0 0 0; font-size: 12px; opacity: 0.8;">{today} | Dual-Strategy Protocol</p>
        </div>
        
        <div style="padding: 15px; border: 1px solid #ddd; border-top: none;">
            <h3 style="border-bottom: 2px solid #eee; padding-bottom: 8px; margin-top: 0;">🚨 Action Items ({len(active_moves)})</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr>
                        <th style="{TH_STYLE}">Ticker</th>
                        <th style="{TH_STYLE}">Strategy</th>
                        <th style="{TH_STYLE}">Action</th>
                        <th style="{TH_STYLE}">Plan (TP / SL)</th>
                        <th style="{TH_STYLE}">Rationale</th>
                    </tr>
                </thead>
                <tbody>
    """

    for order in orders:
        ticker = order.get('ticker')
        action = order.get('action', 'HOLD').upper()
        rec = order.get('final_recommendation', 'AVOID')
        
        # --- DYNAMIC STRATEGY EXTRACTION ---
        # We need to pull the correct data based on the "Scenario"
        
        strategy_label = "❓ UNKNOWN"
        target_dict = {}
        alloc_percent = "0%"
        
        if rec == "POSITION_ONLY":
            strategy_label = "🛡️ POSITION" # Scenario A
            target_dict = order.get('position_trade_analysis', {})
            alloc_percent = "70%"
            bg_color = "#e8f8f5" # Light Green
            
        elif rec == "SWING_ONLY":
            strategy_label = "⚔️ SWING" # Scenario B
            target_dict = order.get('swing_trade_analysis', {})
            alloc_percent = "30%"
            bg_color = "#fef9e7" # Light Yellow
            
        elif rec == "HYBRID":
            strategy_label = "💎 HYBRID" # Scenario C
            target_dict = order.get('position_trade_analysis', {}) # Default to Safety
            alloc_percent = "100%"
            bg_color = "#e8f6f3" # Teal
            
        else: # AVOID or HOLD
            strategy_label = "🚫 AVOID"
            bg_color = "#ffffff"

        # Extract Details
        plan = target_dict.get('execution_plan', {})
        rationale = target_dict.get('rationale', 'No rationale provided.')
        
        tp = plan.get('take_profit', 0)
        sl = plan.get('stop_loss', 0)
        
        # Color Code Action
        act_color = "green" if "OPEN" in action or "UPDATE" in action else "gray"
        if action == "HOLD": act_color = "#999"
        
        # Row HTML
        html_content += f"""
            <tr style="background-color: {bg_color};">
                <td style="{TD_STYLE}"><b>{ticker}</b></td>
                <td style="{TD_STYLE} font-size: 10px;">
                    {strategy_label}<br>
                    <span style="color: #777;">Alloc: {alloc_percent}</span>
                </td>
                <td style="{TD_STYLE} color: {act_color}; font-weight: bold;">{action}</td>
                <td style="{TD_STYLE}">
                    <span style="color: green;">🎯 {tp}</span><br>
                    <span style="color: red;">🛑 {sl}</span>
                </td>
                <td style="{TD_STYLE} font-style: italic;">"{rationale[:80]}..."</td>
            </tr>
        """

    html_content += """
                </tbody>
            </table>
            
            <h3 style="border-bottom: 2px solid #eee; padding-bottom: 8px;">💼 Portfolio Snapshot</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr>
                        <th style="{TH_STYLE}">Asset</th>
                        <th style="{TH_STYLE}">Qty</th>
                        <th style="{TH_STYLE}">Avg Price</th>
                        <th style="{TH_STYLE}">Current</th>
                        <th style="{TH_STYLE}">P/L ($)</th>
                        <th style="{TH_STYLE}">P/L (%)</th>
                    </tr>
                </thead>
                <tbody>
    """

    # --- PORTFOLIO ROWS (Standard) ---
    for pos in portfolio:
        try:
            symbol = pos.symbol
            qty = float(pos.qty)
            avg_entry = float(pos.avg_entry_price)
            current_price = float(pos.current_price)
            unrealized_pl = float(pos.unrealized_pl)
            pl_percent = float(pos.unrealized_plpc) * 100
            
            pl_color = "green" if unrealized_pl >= 0 else "red"
            pl_icon = "🔼" if unrealized_pl >= 0 else "🔻"
            
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
        except: continue

    # --- CEO REPORT SECTION ---
    html_content += f"""
            </tbody>
        </table>
        <br>
        <div style="background-color: #f8f9fa; border: 1px solid #eee; padding: 15px; border-radius: 6px;">
            <h4 style="margin-top: 0; color: #34495e; font-size: 12px; text-transform: uppercase;">🗣️ Senior Manager Notes</h4>
            <p style="font-size: 12px; line-height: 1.5; color: #555; font-style: italic; margin: 0;">
                "{decision.get('ceo_report', 'Session Complete.')}"
            </p>
        </div>
        <p style="font-size: 10px; color: #999; text-align: center; margin-top: 20px;">
            GVQM Protocol v8.0 (Dual-Core) | {datetime.datetime.now().strftime("%H:%M EST")}
        </p>
    </body>
    """

    # --- SEND ---
    try:
        r = resend.Emails.send({
            "from": "onboarding@resend.dev",    
            "to": getattr(config, 'NOTIFY_EMAIL', "your_email@example.com"),
            "subject": subject,
            "html": html_content
        })
        print(f"   ✅ [NOTIFIER] Email Sent! ID: {r.get('id')}")
    except Exception as e:
        print(f"   ❌ [NOTIFIER] Failed to send email: {e}")