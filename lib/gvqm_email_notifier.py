import resend
import config
import datetime

def send_executive_brief(decision, account_info, junior_reports):
    """
    Sends the High-Density HTML Dashboard:
    1. Financial Snapshot (Top)
    2. Trade Ticket (Execution)
    3. Analyst Intel (Context)
    4. CEO Strategy Note (Bottom)
    """
    if not getattr(config, 'RESEND_API_KEY', None):
        print("⚠️ Resend API Key missing. Skipping Brief.")
        return

    print("📧 Sending Executive Briefing via Resend...")
	
    resend.api_key = config.RESEND_API_KEY
    
    today = datetime.date.today().strftime("%b %d, %Y")
    trades = decision.get('final_execution_orders', [])
    
    # Create a lookup map for Junior Reports for O(1) access
    # Logic: We only show Intel for stocks we are actively trading/holding
    junior_map = {r.get('ticker'): r for r in junior_reports}
    
    subject = f"🔔 GVQM Executive Brief: {len(trades)} Actions [{today}]"
		  
		   

    # --- STYLE CONSTANTS ---
    TH_STYLE = "background-color: #f4f4f4; color: #555; font-size: 10px; text-transform: uppercase; padding: 6px; border: 1px solid #ddd;"
    TD_STYLE = "padding: 6px; border: 1px solid #ddd; font-size: 12px;"
    
    # --- 1. FINANCIAL SNAPSHOT (HEADER) ---
    html_content = f"""
    <html>
    <body style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #333; max-width: 800px; margin: auto;">
        
        <div style="background-color: #2c3e50; color: white; padding: 15px; border-radius: 6px 6px 0 0;">
            <table style="width: 100%; border-collapse: collapse; color: white;">
                <tr>
                    <td style="width: 50%;">
                        <h2 style="margin:0;">Good Value Quick Money</h2>
                        <p style="margin:0; font-size: 11px; opacity: 0.8;">{today}</p>
                    </td>
                    <td style="width: 50%; text-align: right;">
                        <span style="font-size: 24px; font-weight: bold;">${float(account_info.equity):,.2f}</span><br>
                        <span style="font-size: 10px; text-transform: uppercase;">Total Equity</span>
                    </td>
                </tr>
            </table>
        </div>

																																	
																												 
																  
			

																																	 
															   
        <table style="width: 100%; border-collapse: collapse; background-color: #ecf0f1; text-align: center; font-size: 12px;">
            <tr>
																			 
                <td style="padding: 8px; border-right: 1px solid #bdc3c7;">
                    <b>💵 Cash:</b> ${float(account_info.cash):,.2f}
                </td>
                <td style="padding: 8px; border-right: 1px solid #bdc3c7;">
                    <b>🚀 Buying Power:</b> ${float(account_info.buying_power):,.2f}
                </td>
                <td style="padding: 8px;">
                    <b>⚡ Active Orders:</b> {len(trades)}
                </td>
            </tr>
        </table>
        
        <br>

        <h3 style="margin-bottom: 5px; color: #2c3e50; border-bottom: 2px solid #2c3e50;">🎫 Execution Ticket</h3>
        <table style="width: 100%; border-collapse: collapse; text-align: left;">
            <thead>
                <tr style="background-color: #f8f9fa;">
                    <th style="{TH_STYLE} width: 10%;">Action</th>
                    <th style="{TH_STYLE} width: 10%;">Ticker</th>
                    <th style="{TH_STYLE}">Limit</th>
                    <th style="{TH_STYLE}">TP</th>
                    <th style="{TH_STYLE}">SL</th>
                    <th style="{TH_STYLE} width: 35%;">Logic / Reason</th>
                </tr>
            </thead>
            <tbody>
    """
    
			
    for order in trades:
        p = order.get('confirmed_params', {})
        action = order.get('action', 'HOLD')
        ticker = order.get('ticker')
        reason = order.get('reason', 'N/A')
		
																															 
														   
	
				  
		 
        
        # Color Coding
        if action == "OPEN_NEW":
            badge = "<span style='color: #27ae60; font-weight: bold;'>🟢 OPEN</span>"
            bg = "#eafaf1"
        elif action == "UPDATE_EXISTING":
            badge = "<span style='color: #2980b9; font-weight: bold;'>♻️ UPDATE</span>"
            bg = "#ebf5fb"
        else:
            badge = "<span style='color: #7f8c8d; font-weight: bold;'>🛑 HOLD</span>"
            bg = "#ffffff"

        html_content += f"""
            <tr style="background-color: {bg};">
                <td style="{TD_STYLE}">{badge}</td>
                <td style="{TD_STYLE}"><b>{ticker}</b></td>
                <td style="{TD_STYLE}">${p.get('buy_limit', '-')}</td>
                <td style="{TD_STYLE}">${p.get('take_profit', '-')}</td>
                <td style="{TD_STYLE}">${p.get('stop_loss', '-')}</td>
                <td style="{TD_STYLE} font-style: italic;">{reason}</td>
            </tr>
        """
						   

    html_content += """
            </tbody>
        </table>
        <br>

        <h3 style="margin-bottom: 5px; color: #8e44ad; border-bottom: 2px solid #8e44ad;">🧠 Analyst Intelligence</h3>
        <table style="width: 100%; border-collapse: collapse; text-align: left;">
            <thead>
                <tr>
                    <th style="{TH_STYLE}">Ticker</th>
                    <th style="{TH_STYLE}">Score</th>
                    <th style="{TH_STYLE}">Valuation</th>
                    <th style="{TH_STYLE}">Status</th>
                    <th style="{TH_STYLE} width: 45%;">The Catalyst (Next 90 Days)</th>
                </tr>
            </thead>
            <tbody>
    """

		   
    for order in trades:
        ticker = order.get('ticker')
		   
        report = junior_map.get(ticker)
        
        if report:
            # Color Code Valuation
            val = report.get('valuation', 'N/A')
            val_color = "#27ae60" if "BARGAIN" in val else ("#c0392b" if "EXPENSIVE" in val else "#f39c12")
            
            # Color Code Status
            stat = report.get('status', 'N/A')
            stat_style = "background-color: #d4edda; color: #155724;" if stat == "SAFE" else "background-color: #f8d7da; color: #721c24;"
            
            html_content += f"""
            <tr>
                <td style="{TD_STYLE}"><b>{ticker}</b></td>
                <td style="{TD_STYLE}"><b>{report.get('conviction_score')}</b>/100</td>
                <td style="{TD_STYLE} color: {val_color}; font-weight: bold;">{val}</td>
                <td style="{TD_STYLE}"><span style="padding: 2px 4px; border-radius: 3px; font-size: 10px; font-weight: bold; {stat_style}">{stat}</span></td>
                <td style="{TD_STYLE}">{report.get('catalyst') or report.get('rebound_potential') or 'No specific catalyst.'}</td>
																					 
					 
            </tr>
            """
    
    html_content += f"""
            </tbody>
        </table>
        <br>

					   
        <div style="background-color: #fcfcfc; border-left: 4px solid #34495e; padding: 15px; margin-top: 10px;">
            <h4 style="margin-top: 0; color: #34495e;">🗣️ CEO Strategy Note</h4>
            <p style="font-size: 13px; line-height: 1.5; color: #555;">
                "{decision.get('ceo_report', 'No report available.')}"
            </p>
        </div>

        <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="font-size: 10px; color: #999; text-align: center;">
            Generated by GVQM Alpha Protocol v3.0 | Time: {datetime.datetime.now().strftime("%H:%M EST")}
        </p>
    </body>
    </html>
    """
    
								 
										
	 

    # --- SEND ---
		   
	 

    try:
        r = resend.Emails.send({
			  
            "from": config.EMAIL_SENDER,
            "to": config.EMAIL_RECIPIENT,
            "subject": subject,
            "html": html_content
        })
        print(f"✅ Email sent successfully. RESEND ID: {r.get('id')}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")