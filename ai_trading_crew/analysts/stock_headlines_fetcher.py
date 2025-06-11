import datetime
import time
import pytz
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Union, Tuple, Optional
from dataclasses import dataclass
import re
import json
import dateutil.parser
from ai_trading_crew.utils.company_info import get_company_name
import os

@dataclass
class NewsItem:
    headline: str
    url: str
    source: str
    published_at: datetime.datetime

def parse_time_input(time_input: Union[str, int]) -> datetime.datetime:
    """Convert input time to datetime object in UTC"""
    est = pytz.timezone('US/Eastern')
    
    if isinstance(time_input, str):
        try:
            dt = datetime.datetime.strptime(time_input, "%Y-%m-%d %H:%M")
        except ValueError:
            dt = datetime.datetime.strptime(time_input, "%Y-%m-%d")
            dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        dt = est.localize(dt)
        return dt.astimezone(pytz.UTC)
    elif isinstance(time_input, int):
        return datetime.datetime.fromtimestamp(time_input, pytz.UTC)
    else:
        raise ValueError("Time input must be a string in format 'YYYY-MM-DD HH:MM' or a Unix timestamp")

def fetch_finviz_news(ticker: str, start_time: datetime.datetime) -> List[NewsItem]:
    """Fetch news from Finviz"""
    url = f"https://finviz.com/quote.ashx?t={ticker}&p=d"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Referer': 'https://www.google.com/'
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return []
        with open("finviz_response.html", "w", encoding="utf-8") as f:
            f.write(response.text)
        soup = BeautifulSoup(response.text, 'html.parser')
        news_table = soup.find('table', class_='fullview-news-outer')
        if not news_table:
            # Clean up the debug file
            try:
                os.remove("finviz_response.html")
            except OSError:
                pass
            return []
        rows = news_table.find_all('tr')
        results = []
        est = pytz.timezone('US/Eastern')
        current_date = datetime.datetime.now(est).date()
        now = datetime.datetime.now(est)
        current_date_reference = None
        for row in rows:
            try:
                cells = row.find_all('td')
                if len(cells) < 2:
                    continue
                date_cell = cells[0]
                date_str = date_cell.text.strip()
                title_cell = cells[1]
                link = title_cell.find('a')
                if not link:
                    continue
                headline = link.text.strip()
                article_url = link.get('href')
                if article_url and article_url.startswith('/'):
                    article_url = f"https://finviz.com{article_url}"
                source_text = title_cell.find('span', class_='news_source')
                source = "Finviz"
                if source_text:
                    source_str = source_text.text.strip()
                    if source_str.startswith('(') and source_str.endswith(')'):
                        source = source_str[1:-1]
                article_date = None
                if "Today" in date_str:
                    time_part = date_str.replace("Today", "").strip()
                    current_date_reference = current_date
                    if ":" in time_part:
                        if "AM" in time_part or "PM" in time_part:
                            try:
                                time_obj = datetime.datetime.strptime(time_part, "%I:%M%p").time()
                            except ValueError:
                                try:
                                    time_obj = datetime.datetime.strptime(time_part, "%I:%M %p").time()
                                except ValueError:
                                    continue
                        else:
                            try:
                                hour, minute = map(int, time_part.split(':'))
                                time_obj = datetime.time(hour, minute)
                            except ValueError:
                                continue
                        article_date = datetime.datetime.combine(current_date, time_obj)
                        article_date = est.localize(article_date)
                elif "Yesterday" in date_str:
                    time_part = date_str.replace("Yesterday", "").strip()
                    yesterday = current_date - datetime.timedelta(days=1)
                    current_date_reference = yesterday
                    if ":" in time_part:
                        if "AM" in time_part or "PM" in time_part:
                            try:
                                time_obj = datetime.datetime.strptime(time_part, "%I:%M%p").time()
                            except ValueError:
                                try:
                                    time_obj = datetime.datetime.strptime(time_part, "%I:%M %p").time()
                                except ValueError:
                                    continue
                        else:
                            try:
                                hour, minute = map(int, time_part.split(':'))
                                time_obj = datetime.time(hour, minute)
                            except ValueError:
                                continue
                        article_date = datetime.datetime.combine(yesterday, time_obj)
                        article_date = est.localize(article_date)
                elif "-" in date_str and len(date_str.split("-")) == 3:
                    parts = date_str.split()
                    date_part = parts[0]
                    time_part = parts[1] if len(parts) > 1 else None
                    try:
                        month_str, day_str, year_str = date_part.split("-")
                        month_map = {
                            "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
                            "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
                        }
                        month_num = month_map.get(month_str, 1)
                        day_num = int(day_str)
                        year_num = int(year_str)
                        if year_num < 100:
                            year_num += 2000
                        date_obj = datetime.date(year_num, month_num, day_num)
                        current_date_reference = date_obj
                        if time_part:
                            if ":" in time_part:
                                if "AM" in time_part or "PM" in time_part:
                                    hour_str, minute_sec = time_part.split(":")
                                    hour = int(hour_str)
                                    minute_str = minute_sec
                                    for suffix in ["AM", "PM", " AM", " PM"]:
                                        if minute_str.endswith(suffix):
                                            minute_str = minute_str[:-len(suffix)]
                                            break
                                    minute = int(minute_str)
                                    if ("PM" in minute_sec or " PM" in minute_sec) and hour < 12:
                                        hour += 12
                                    if ("AM" in minute_sec or " AM" in minute_sec) and hour == 12:
                                        hour = 0
                                    article_date = datetime.datetime(year_num, month_num, day_num, hour, minute)
                                else:
                                    hour, minute = map(int, time_part.split(":"))
                                    article_date = datetime.datetime(year_num, month_num, day_num, hour, minute)
                            else:
                                article_date = datetime.datetime(year_num, month_num, day_num, 12, 0)
                        else:
                            article_date = datetime.datetime(year_num, month_num, day_num, 12, 0)
                        article_date = est.localize(article_date)
                    except Exception:
                        continue
                elif ":" in date_str and ("AM" in date_str or "PM" in date_str) and current_date_reference:
                    try:
                        try:
                            time_obj = datetime.datetime.strptime(date_str, "%I:%M%p").time()
                        except ValueError:
                            try:
                                time_obj = datetime.datetime.strptime(date_str, "%I:%M %p").time()
                            except ValueError:
                                continue
                        ref_date = current_date_reference
                        if isinstance(ref_date, datetime.datetime):
                            ref_date = ref_date.date()
                        article_date = datetime.datetime.combine(ref_date, time_obj)
                        article_date = est.localize(article_date)
                    except Exception:
                        continue
                if article_date is None:
                    continue
                article_date_utc = article_date.astimezone(pytz.UTC)
                if article_date_utc >= start_time:
                    results.append(NewsItem(
                        headline=headline,
                        url=article_url,
                        source=source,
                        published_at=article_date_utc
                    ))
            except Exception:
                continue
        
        # Clean up the debug file after processing
        try:
            os.remove("finviz_response.html")
        except OSError:
            pass
            
        return results
    except Exception:
        # Clean up the debug file on exception
        try:
            os.remove("finviz_response.html")
        except OSError:
            pass
        return []

def fetch_stock_news(ticker: str, start_time: Union[str, int]) -> List[NewsItem]:
    """
    Fetch stock news from multiple sources including MarketWatch
    """
    start_datetime = parse_time_input(start_time)
    finviz_news = fetch_finviz_news(ticker, start_datetime)

    all_news = finviz_news
    filtered_news = []
    for news_item in all_news:
        if "/topic/" in news_item.url or "/category/" in news_item.url:
            continue
        if news_item.headline in ["More AAPL News >", "More News >"]:
            continue
        filtered_news.append(news_item)
        
    # Simple deduplication - only exact headline matches and URL matches
    seen_urls = set()
    seen_exact_headlines = set()
    deduplicated_news = []
    
    for news_item in filtered_news:
        # Only deduplicate exact same headlines or same URLs
        if news_item.url in seen_urls:
            continue
        if news_item.headline in seen_exact_headlines:
            continue
            
        seen_exact_headlines.add(news_item.headline)
        seen_urls.add(news_item.url)
        deduplicated_news.append(news_item)
        
    deduplicated_news.sort(key=lambda x: x.published_at, reverse=True)
    return deduplicated_news

def get_news_context(symbol: str, start_time: str) -> str:
    """
    Get formatted news context for a stock symbol since a specific time.
    """
    news_items = fetch_stock_news(symbol, start_time)
    company_name = get_company_name(symbol)
    if not news_items:
        return f"No news found for {company_name} since {start_time}"
    
    # Create the formatted news content with consistent line breaks
    result = f"News for {company_name} since {start_time}:\n\n"
    for i, item in enumerate(news_items):
        est = pytz.timezone('US/Eastern')
        published_at_est = item.published_at.astimezone(est)
        formatted_date = published_at_est.strftime("%Y-%m-%d %H:%M:%S %Z")
        
        # Clean up the headline text - replace problematic Unicode characters
        headline = item.headline
        # Fix curly single quotes
        headline = headline.replace('\u2019', "'").replace('\u2018', "'")
        headline = headline.replace('\u2032', "'").replace('\u02bc', "'")
        headline = headline.replace('â\x80\x99', "'")
        
        # Fix curly double quotes
        headline = headline.replace('\u201c', '"').replace('\u201d', '"')
        headline = headline.replace('â\x80\x9c', '"').replace('â\x80\x9d', '"')
        
        # Fix other common problematic characters
        headline = headline.replace('\u2013', '-').replace('\u2014', '--')  # en/em dashes
        headline = headline.replace('\u2026', '...').replace('\u00a0', ' ')  # ellipsis, non-breaking space
        headline = headline.replace('\u00ad', '')  # soft hyphen
        
        # Remove any remaining non-ascii characters
        headline = ''.join(c if ord(c) < 128 else ' ' for c in headline)
        headline = headline.replace('   ', ' ').replace('  ', ' ').strip()  # Clean up extra spaces
        
        # Ensure proper formatting with normalized line breaks
        result += f"{i+1}. [{item.source}] {headline}\n"
        result += f"   Published: {formatted_date}\n"
        result += f"   URL: {item.url}\n\n"
    
    # Ensure consistent encoding and line endings
    result = result.replace('\r\n', '\n').replace('\r', '\n')
    
    # Make a final pass to ensure only ASCII characters remain
    result = result.encode('ascii', 'replace').decode('ascii')
    
    return result