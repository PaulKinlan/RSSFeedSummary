import feedparser
from datetime import datetime
import logging
from app import db, scheduler
from models import Feed, Article
from ai_summarizer import generate_summary
from email_service import send_daily_digest
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def process_feeds(feeds=None):
    """Process RSS feeds and generate summaries for new articles."""
    if feeds is None:
        feeds = Feed.query.all()
    
    processed_count = 0
    error_count = 0
    
    for feed in feeds:
        try:
            logger.info(f"Processing feed: {feed.url}")
            parsed_feed = feedparser.parse(feed.url)
            
            if hasattr(parsed_feed, 'status') and parsed_feed.status != 200:
                logger.error(f"Error fetching feed {feed.url}: HTTP {parsed_feed.status}")
                error_count += 1
                continue
                
            feed.title = parsed_feed.feed.get('title', urlparse(feed.url).netloc)
            feed.last_checked = datetime.utcnow()
            
            for entry in parsed_feed.entries:
                try:
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
                            processed_count += 1
                        
                        db.session.add(article)
                        logger.info(f"Added new article: {article.title}")
                
                except Exception as e:
                    logger.error(f"Error processing entry in feed {feed.url}: {str(e)}")
                    error_count += 1
                    continue
            
            db.session.commit()
            
        except Exception as e:
            logger.error(f"Error processing feed {feed.url}: {str(e)}")
            error_count += 1
            continue
    
    logger.info(f"Feed processing complete. Processed {processed_count} new articles. Encountered {error_count} errors.")
    return processed_count, error_count

def schedule_tasks():
    """Schedule periodic tasks for feed processing and email digests."""
    try:
        # Schedule feed processing every hour
        scheduler.add_job(
            func=process_feeds,
            trigger='interval',
            hours=1,
            id='process_feeds',
            replace_existing=True
        )
        logger.info("Scheduled feed processing task")
        
        # Schedule daily digest emails at midnight
        scheduler.add_job(
            func=send_daily_digest,
            trigger='cron',
            hour=0,
            minute=0,
            id='send_daily_digest',
            replace_existing=True
        )
        logger.info("Scheduled daily digest task")
        
    except Exception as e:
        logger.error(f"Error scheduling tasks: {str(e)}")
        raise
