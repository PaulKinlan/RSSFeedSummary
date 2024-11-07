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
    from app import app
    
    with app.app_context():
        if feeds is None:
            feeds = Feed.query.all()
        
        for feed in feeds:
            try:
                logger.info(f"Processing feed: {feed.url}")
                parsed_feed = feedparser.parse(feed.url)
                
                # Update feed status first
                if hasattr(parsed_feed, 'status') and parsed_feed.status != 200:
                    feed.status = 'error'
                    feed.error_message = f"HTTP Error {parsed_feed.status}"
                    db.session.commit()
                    continue
                
                # Set title and status
                if hasattr(parsed_feed.feed, 'title'):
                    feed.title = parsed_feed.feed.title
                else:
                    feed.title = urlparse(feed.url).netloc
                
                feed.last_checked = datetime.utcnow()
                feed.status = 'active'  # Set status to active
                feed.error_message = None
                db.session.commit()  # Commit changes immediately
                
                # Process entries (limited to 10)
                entries = parsed_feed.entries[:10]
                for entry in entries:
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
                            
                            summary_result = generate_summary(entry.title, entry.get('description', ''))
                            if summary_result:
                                article.summary = summary_result['summary']
                                article.critique = summary_result['critique']
                                article.processed = True
                            
                            db.session.add(article)
                            db.session.commit()  # Commit after each article
                            logger.info(f"Added new article: {article.title}")
                    
                    except Exception as e:
                        logger.error(f"Error processing entry: {str(e)}")
                        continue
                
            except Exception as e:
                logger.error(f"Error processing feed {feed.url}: {str(e)}")
                feed.status = 'error'
                feed.error_message = str(e)
                db.session.commit()
                continue
        
        logger.info(f"Feed processing complete.")

def schedule_feed_processing(feed_id):
    """Schedule immediate processing of a specific feed."""
    from app import app
    
    def process_with_context():
        with app.app_context():
            process_feeds([Feed.query.get(feed_id)])
    
    scheduler.add_job(
        func=process_with_context,
        id=f'process_feed_{feed_id}',
        replace_existing=True
    )
    logger.info(f"Scheduled processing for feed ID: {feed_id}")

def schedule_tasks():
    """Schedule periodic tasks for feed processing and email digests."""
    from app import app
    
    def process_with_context():
        with app.app_context():
            process_feeds()
    
    def send_digest_with_context():
        with app.app_context():
            send_daily_digest()
            
    try:
        # Schedule feed processing every hour
        scheduler.add_job(
            func=process_with_context,
            trigger='interval',
            hours=1,
            id='process_feeds',
            replace_existing=True
        )
        logger.info("Scheduled feed processing task")
        
        # Schedule daily digest emails at midnight
        scheduler.add_job(
            func=send_digest_with_context,
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
