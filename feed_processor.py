import feedparser
from datetime import datetime
from app import db, scheduler
from models import Feed, Article
from ai_summarizer import generate_summary
from email_service import send_daily_digest
from urllib.parse import urlparse

def process_feeds(feeds=None):
    if feeds is None:
        feeds = Feed.query.all()
    
    for feed in feeds:
        try:
            parsed_feed = feedparser.parse(feed.url)
            feed.title = parsed_feed.feed.get('title', urlparse(feed.url).netloc)
            feed.last_checked = datetime.utcnow()
            
            for entry in parsed_feed.entries:
                # Check if article already exists
                existing = Article.query.filter_by(
                    url=entry.link,
                    feed_id=feed.id
                ).first()
                
                if not existing:
                    published = entry.get('published_parsed', None)
                    if published:
                        published = datetime(*published[:6])
                    
                    article = Article(
                        title=entry.title,
                        url=entry.link,
                        content=entry.get('description', ''),
                        published_date=published,
                        feed_id=feed.id
                    )
                    
                    # Generate summary and critique using Gemini
                    summary_result = generate_summary(entry.title, entry.get('description', ''))
                    if summary_result:
                        article.summary = summary_result['summary']
                        article.critique = summary_result['critique']
                        article.processed = True
                    
                    db.session.add(article)
            
            db.session.commit()
            
        except Exception as e:
            print(f"Error processing feed {feed.url}: {str(e)}")
            continue

def schedule_tasks():
    # Schedule feed processing every hour
    scheduler.add_job(
        func=process_feeds,
        trigger='interval',
        hours=1,
        id='process_feeds'
    )
    
    # Schedule daily digest emails at midnight
    scheduler.add_job(
        func=send_daily_digest,
        trigger='cron',
        hour=0,
        minute=0,
        id='send_daily_digest'
    )
