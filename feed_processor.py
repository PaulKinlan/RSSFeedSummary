import feedparser
from datetime import datetime, timedelta
import logging
from app import db, scheduler
from models import Feed, Article, User, Tag, Category
from ai_summarizer import generate_summary, get_or_create_tag, get_or_create_category
from email_service import send_daily_digest, send_weekly_digest
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def cleanup_expired_accounts():
    """Delete unverified accounts with expired verification tokens."""
    from app import app, db
    from models import User
    from datetime import datetime
    
    with app.app_context():
        try:
            # Find unverified accounts with expired tokens
            expired_accounts = User.query.filter(
                User.email_verified == False,
                User.verification_token.is_not(None),
                User.verification_token_expires <= datetime.utcnow()
            ).all()
            
            deleted_count = 0
            for user in expired_accounts:
                try:
                    db.session.delete(user)
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"Error deleting expired account {user.id}: {str(e)}")
                    continue
            
            if deleted_count > 0:
                db.session.commit()
                logger.info(f"Deleted {deleted_count} expired unverified accounts")
                
        except Exception as e:
            logger.error(f"Error in cleanup_expired_accounts: {str(e)}")
            raise

def process_feeds(feeds=None):

    """Process RSS feeds and generate summaries for new articles."""
    from app import app, db
    
    with app.app_context():
        try:
            if feeds is None:
                feeds = Feed.query.all()
                feed_ids = [feed.id for feed in feeds]
            else:
                feed_ids = [feed.id for feed in feeds]
            
            for feed_id in feed_ids:
                try:
                    feed = Feed.query.get(feed_id)
                    if not feed:
                        continue
                        
                    logger.info(f"Processing feed: {feed.url}")
                    parsed_feed = feedparser.parse(feed.url)
                    
                    if hasattr(parsed_feed.feed, 'title'):
                        feed.title = parsed_feed.feed.title[:200]  # Truncate feed title
                    else:
                        feed.title = urlparse(feed.url).netloc[:200]  # Truncate netloc
                    
                    feed.last_checked = datetime.utcnow()
                    
                    # Get the user object for customized summary generation
                    user = User.query.get(feed.user_id)
                    if not user:
                        continue
                    
                    # Process entries (limited to 10)
                    entries = parsed_feed.entries[:10]
                    processed_count = 0
                    
                    for entry in entries:
                        try:
                            existing = Article.query.filter_by(
                                url=entry.link,
                                feed_id=feed.id
                            ).first()
                            
                            if not existing:
                                published = entry.get('published_parsed', None)
                                if published:
                                    published = datetime(*published[:6])
                                
                                article = Article(
                                    title=entry.title[:200] if entry.title else '',  # Truncate to 200 chars
                                    url=entry.link,
                                    content=entry.get('description', ''),
                                    published_date=published,
                                    feed_id=feed.id
                                )
                                
                                summary_result = generate_summary(
                                    entry.title, 
                                    entry.get('description', ''),
                                    user
                                )
                                
                                if summary_result:
                                    article.summary = summary_result['summary']
                                    article.critique = summary_result.get('critique')
                                    
                                    # Process tags
                                    if 'tags' in summary_result:
                                        for tag_name in summary_result['tags']:
                                            tag = get_or_create_tag(tag_name)
                                            article.tags.append(tag)
                                    
                                    # Process categories
                                    if 'categories' in summary_result:
                                        for category_name in summary_result['categories']:
                                            category = get_or_create_category(category_name)
                                            article.categories.append(category)
                                    
                                    article.processed = True
                                    processed_count += 1
                                
                                db.session.add(article)
                                db.session.commit()
                                logger.info(f"Added new article: {article.title}")
                        
                        except Exception as e:
                            logger.error(f"Error processing entry: {str(e)}")
                            continue
                    
                    # Update feed status
                    feed = Feed.query.get(feed_id)
                    if feed and processed_count > 0:
                        feed.status = 'active'
                        feed.error_message = None
                        db.session.commit()
                        logger.info(f"Feed {feed.url} marked as active")
                    
                except Exception as e:
                    logger.error(f"Error processing feed {feed_id}: {str(e)}")
                    feed = Feed.query.get(feed_id)
                    if feed:
                        feed.status = 'error'
                        feed.error_message = str(e)
                        db.session.commit()
                    continue
            
            logger.info("Feed processing complete.")
            
        except Exception as e:
            logger.error(f"Error in process_feeds: {str(e)}")
            raise

def schedule_feed_processing(feed_id):
    """Schedule immediate processing of a specific feed."""
    from app import app
    
    def process_with_context():
        with app.app_context():
            feed = Feed.query.get(feed_id)
            if feed:
                process_feeds([feed])
    
    job_id = f'process_feed_{feed_id}'
    try:
        scheduler.remove_job(job_id)
    except:
        pass
    
    # Add new job with improved settings
    scheduler.add_job(
        func=process_with_context,
        id=job_id,
        next_run_time=datetime.now(),
        misfire_grace_time=900,  # 15 minutes grace time
        coalesce=True,
        max_instances=1
    )
    logger.info(f"Scheduled immediate processing for feed ID: {feed_id}")

def schedule_tasks():
    """Schedule periodic tasks for feed processing and email digests."""
    from app import app
    
    def process_with_context():
        with app.app_context():
            try:
                process_feeds()
            except Exception as e:
                logger.error(f"Error in scheduled feed processing: {str(e)}")
    
    def send_daily_digest_with_context():
        with app.app_context():
            try:
                send_daily_digest()
            except Exception as e:
                logger.error(f"Error sending daily digest: {str(e)}")
    
    def send_weekly_digest_with_context():
        with app.app_context():
            try:
                send_weekly_digest()
            except Exception as e:
                logger.error(f"Error sending weekly digest: {str(e)}")
    
    def cleanup_expired_accounts_with_context():
        with app.app_context():
            try:
                cleanup_expired_accounts()
            except Exception as e:
                logger.error(f"Error cleaning up expired accounts: {str(e)}")
    
    try:
        # Remove existing jobs if they exist
        for job_id in ['process_feeds', 'send_daily_digest', 'send_weekly_digest']:
            try:
                scheduler.remove_job(job_id)
            except:
                pass
        
        # Schedule feed processing every hour with improved settings
        scheduler.add_job(
            func=process_with_context,
            trigger='interval',
            hours=1,
            id='process_feeds',
            replace_existing=True,
            next_run_time=datetime.now(),
            misfire_grace_time=900,  # 15 minutes grace time
            coalesce=True,
            max_instances=1
        )
        logger.info("Scheduled feed processing task")
        
        # Schedule daily digest emails at midnight
        scheduler.add_job(
            func=send_daily_digest_with_context,
            trigger='cron',
            hour=0,
            minute=0,
            id='send_daily_digest',
            replace_existing=True,
            misfire_grace_time=3600,  # 1 hour grace time
            coalesce=True
        )
        logger.info("Scheduled daily digest task")
        
        # Schedule weekly digest emails at midnight on Sundays
        scheduler.add_job(
            func=send_weekly_digest_with_context,
            trigger='cron',
            day_of_week='sun',
            hour=0,
            minute=0,
            id='send_weekly_digest',
            replace_existing=True,
            misfire_grace_time=3600,  # 1 hour grace time
            coalesce=True
        )
        logger.info("Scheduled weekly digest task")
        
        # Schedule cleanup of expired unverified accounts (every 6 hours)
        scheduler.add_job(
            func=cleanup_expired_accounts_with_context,
            trigger='interval',
            hours=6,
            id='cleanup_expired_accounts',
            replace_existing=True,
            next_run_time=datetime.now(),
            misfire_grace_time=900,  # 15 minutes grace time
            coalesce=True,
            max_instances=1
        )
        logger.info("Scheduled expired accounts cleanup task")
        
    except Exception as e:
        logger.error(f"Error scheduling tasks: {str(e)}")
        raise
