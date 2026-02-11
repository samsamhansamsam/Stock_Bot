import yfinance as yf
import requests
import google.generativeai as genai
import os
import datetime
import feedparser
import csv

# 🛡️ 설정 (GitHub Secrets)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# Gemini 설정
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-3-flash-preview')

def get_market_data():
    """주요 시장 지수 및 매크로 지표 조회"""
    tickers = {
        "^GSPC": "🇺🇸 S&P 500",
        "^IXIC": "🇺🇸 Nasdaq",
        "^TNX": "🇺🇸 10Y Treasury",
        "DX-Y.NYB": "💵 Dollar Index",
        "CL=F": "🛢️ Crude Oil (WTI)",
        "GC=F": "🥇 Gold"
    }
    
    data_str = ""
    for ticker, name in tickers.items():
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if len(hist) < 2:
                continue
            
            close = hist['Close'].iloc[-1]
            prev_close = hist['Close'].iloc[-2]
            change = ((close - prev_close) / prev_close) * 100
            
            icon = "🔺" if change > 0 else "🔻"
            data_str += f"{name}: {close:.2f} ({icon} {change:+.2f}%)\n"
        except:
            continue
            
    return data_str

def get_sector_performance():
    """섹터 ETF 등락률 조회 및 뉴스 검색"""
    # 주요 섹터 ETF (SPDR)
    sectors = {
        "XLK": "Technology",
        "XLF": "Financials",
        "XLV": "Healthcare",
        "XLE": "Energy",
        "XLY": "Consumer Discretionary",
        "XLP": "Consumer Staples",
        "XLI": "Industrials",
        "XLC": "Communication Services",
        "XLU": "Utilities",
        "XLB": "Materials",
        "XLRE": "Real Estate"
    }
    
    sector_data = []
    
    for ticker, name in sectors.items():
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if len(hist) < 2:
                continue
                
            change = ((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100
            
            # 모든 섹터 데이터 저장 (CSV용)
            sector_data.append({
                "ticker": ticker,
                "name": name,
                "change": change,
                "news": "" 
            })

            # 변동폭이 큰 섹터만 뉴스 검색 (리포트용)
            if abs(change) > 0.5: 
                news = stock.news[:2]
                news_summary = ""
                for n in news:
                    news_summary += f"- [{n['title']}]({n['link']})\n"
                sector_data[-1]["news"] = news_summary

        except:
            continue
    
    # 등락률 순으로 정렬
    sector_data.sort(key=lambda x: x['change'], reverse=True)
    return sector_data

def get_trending_discussions(limit=3):
    """Reddit(r/stocks, r/economics)에서 인기 게시글 가져오기"""
    urls = [
        "https://www.reddit.com/r/stocks/top/.rss?t=day",
        "https://www.reddit.com/r/economics/top/.rss?t=day"
    ]
    
    trending = []
    for url in urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:limit]:
                trending.append(f"- [{entry.title}]({entry.link})")
        except:
            continue
            
    return "\n".join(trending)

def save_to_csv(sector_data):
    """섹터 데이터를 daily_sector_trend.csv 파일에 저장 (누적)"""
    file_name = 'daily_sector_trend.csv'
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    
    file_exists = os.path.isfile(file_name)
    
    with open(file_name, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            # 헤더 작성
            writer.writerow(['Date', 'Sector', 'Ticker', 'Change(%)'])
        
        for s in sector_data:
            writer.writerow([today, s['name'], s['ticker'], round(s['change'], 2)])
            
    print(f"✅ Saved sector data to {file_name}")

def summarize_with_gemini(macro_data, sector_data, trending_text):
    """Gemini로 시장 브리핑 작성"""
    if not GEMINI_API_KEY:
        return "⚠️ Gemini API Key Missing"
    
    # 상위 5개 섹터만 리포트에 포함
    sector_text = ""
    for s in sector_data[:5]:
        if abs(s['change']) > 0.5: # 유의미한 변동만
            icon = "🔥" if s['change'] > 0 else "❄️"
            sector_text += f"{icon} **{s['name']}** ({s['change']:+.2f}%)\nNews:\n{s['news']}\n"
        
    prompt = f"""
    당신은 월가(Wall Street)의 베테랑 애널리스트입니다.
    아래 시장 데이터를 바탕으로 투자자들을 위한 '모닝 브리핑'을 작성해주세요.
    
    [Macro Indicators]
    {macro_data}
    
    [Key Sectors & News]
    {sector_text}

    [Trending Discussions (Investment Community)]
    {trending_text}
    
    [요청사항]
    1. **시장 총평**: 오늘 시장의 분위기를 한 줄로 요약해주세요. (이모지 포함)
    2. **매크로 분석**: 금리, 유가, 달러의 움직임이 시장에 미친 영향을 분석해주세요.
    3. **섹터 포커스**: 가장 눈에 띄는 섹터(상승/하락) 2~3개를 골라, 특정 종목보다는 '섹터 전반'의 이슈(규제, 원자재, 트렌드 등)를 중심으로 상승/하락 원인을 분석해주세요.
    4. **커뮤니티 핫이슈**: 'Trending Discussions' 내용을 참고하여, 현재 개인 투자자들이 가장 관심 있어 하는 이슈나 논쟁 거리를 1~2줄로 요약해주세요.
    5. **투자 인사이트**: 그래서 내일은 어떤 섹터를 주목해야 할지, 혹은 어떤 이슈를 조심해야 할지 조언해주세요.
    6. 톤앤매너: 전문적이지만 쉽고 간결하게(개조식). 한국어로 작성.
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Gemini Error: {e}"

def send_telegram(message):
    print("🚀 Attempting to send Telegram message...")
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("❌ Telegram tokens are missing in environment variables!")
        print(f"Token present: {bool(TELEGRAM_TOKEN)}")
        print(f"Chat ID present: {bool(CHAT_ID)}")
        print("--- Generated Message Content (Not Sent) ---")
        print(message)
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': True
    }
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("✅ Telegram message sent successfully.")
        else:
            print(f"❌ Failed to send Telegram message. Status Code: {response.status_code}")
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"❌ Error sending Telegram message: {e}")

def main():
    print("Fetching Market Data...")
    macro_data = get_market_data()
    
    print("Fetching Sector Data...")
    sector_data = get_sector_performance()
    
    print("Fetching Trending Discussions...")
    trending_text = get_trending_discussions()
    
    print("Saving Data locally...")
    save_to_csv(sector_data)
    
    print("Generating AI Report...")
    report = summarize_with_gemini(macro_data, sector_data, trending_text)
    
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    final_msg = f"🗽 **{today} Global Market Brief** 🗽\n\n{report}"
    
    send_telegram(final_msg)

if __name__ == "__main__":
    main()
