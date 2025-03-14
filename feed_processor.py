import os
import feedparser
import logging
from datetime import datetime, timedelta
from urllib.parse import urlparse
from sqlalchemy import or_
from app import scheduler, db
from models import User, Feed, Article, Tag, Category
from ai_summarizer import generate_summary, get_or_create_tag, get_or_create_category
from email_service import send_daily_digest, send_weekly_digest

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def cleanup_expired_accounts():
    """Delete unverified accounts with expired verification tokens."""
    from app import db
    from models import User, Feed, Article
    from datetime import datetime
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Find unverified accounts with expired tokens
        expired_accounts = User.query.filter(
            User.email_verified == False,
            User.verification_token.is_not(None),
            User.verification_token_expires <= datetime.utcnow()).all()

        if not expired_accounts:
            logger.info("No expired unverified accounts found")
            return

        logger.info(
            f"Found {len(expired_accounts)} expired unverified accounts to be cleaned up"
        )
        logger.info("Starting cleanup process...")
        deleted_count = 0

        for user in expired_accounts:
            try:
                logger.info(
                    f"Processing expired account - User ID: {user.id}, Email: {user.email}"
                )

                # Count associated data for logging
                feeds = Feed.query.filter_by(user_id=user.id).all()
                feed_count = len(feeds)
                article_count = 0

                # Delete all associated articles first
                for feed in feeds:
                    count = Article.query.filter_by(
                        feed_id=feed.id).delete()
                    article_count += count
                    logger.info(
                        f"Deleted {count} articles for feed ID: {feed.id}")

                # Then delete all feeds
                Feed.query.filter_by(user_id=user.id).delete()
                logger.info(
                    f"Deleted {feed_count} feeds for user ID: {user.id}")

                # Finally delete the user
                db.session.delete(user)
                deleted_count += 1

                # Commit after each successful user deletion
                db.session.commit()
                logger.info(
                    f"Successfully deleted expired unverified user ID: {user.id} with {feed_count} feeds and {article_count} articles"
                )

            except Exception as e:
                logger.error(
                    f"Error deleting expired account {user.id}: {str(e)}")
                db.session.rollback()
                continue

        logger.info(
            f"Cleanup completed: Deleted {deleted_count} expired unverified accounts"
        )
        logger.info(f"Cleanup completed at: {datetime.utcnow()}")

    except Exception as e:
        logger.error(f"Error in cleanup_expired_accounts: {str(e)}")
        db.session.rollback()
        raise


def process_feeds(feeds=None, max_retries=3, webhook_triggered=False):
    """Process RSS feeds and generate summaries for new articles with retry mechanism.
    
    Args:
        feeds: Optional list of Feed objects to process. If None, all eligible feeds are processed.
        max_retries: Maximum number of retry attempts for failed feeds.
        webhook_triggered: Whether this processing was triggered by a webhook.
    """
    from app import app, db
    import time
    from webhook_service import register_webhook, generate_callback_url

    with app.app_context():
        try:
            start_time = time.time()
            logger.info(
                f"Starting feed processing cycle (webhook triggered: {webhook_triggered})"
            )

            # Application URL for webhook callbacks
            app_url = os.environ.get('APPLICATION_URL', 'https://tldr.express')
            callback_url = generate_callback_url(app_url)

            if feeds is None:
                # Get feeds that haven't been checked in the last hour
                one_hour_ago = datetime.utcnow() - timedelta(hours=1)
                
                # Only get feeds for verified and unexpired accounts
                query = Feed.query.join(User).filter(
                    User.email_verified == True,  # Only verified users
                    or_(
                        User.verification_token.is_(
                            None),  # Users that completed verification
                        User.verification_token_expires > datetime.utcnow(
                        )  # Users still within verification window
                    )).filter(
                        or_(
                            Feed.processing_attempts
                            < max_retries,  # Still within retry limit
                            Feed.status ==
                            'active'  # Or currently active feeds
                        ),
                        or_(
                            Feed.last_checked == None,  # Never checked before
                            Feed.last_checked < one_hour_ago  # Or not checked in the last hour
                        )
                    ).order_by(Feed.last_checked.asc().nullsfirst())

                try:
                    feeds = query.all()
                    feed_ids = [feed.id for feed in feeds]
                    logger.info(
                        f"Found {len(feeds)} feeds to process from verified and unexpired accounts"
                    )
                    logger.info(f"Feed IDs to process: {feed_ids}")
                except Exception as e:
                    logger.error(f"Error querying feeds: {str(e)}")
                    raise
            else:
                # For specific feeds, still check if they belong to valid accounts
                feed_ids = []
                one_hour_ago = datetime.utcnow() - timedelta(hours=1)
                for feed in feeds:
                    user = User.query.get(feed.user_id)
                    # Check if feed hasn't been checked in the last hour
                    can_process = (feed.last_checked is None or feed.last_checked < one_hour_ago)
                    
                    if user and user.email_verified and (
                            user.verification_token is None
                            or user.verification_token_expires
                            > datetime.utcnow()) and (
                                feed.processing_attempts < max_retries
                                or feed.status == 'active') and can_process:
                        feed_ids.append(feed.id)

            for feed_id in feed_ids:
                try:
                    feed = Feed.query.get(feed_id)
                    if not feed:
                        logger.warning(f"Feed {feed_id} not found, skipping")
                        continue

                    # Log processing attempt details
                    logger.info(f"Processing feed ID {feed_id}: {feed.url}")
                    logger.info(
                        f"Previous attempts: {feed.processing_attempts}, Status: {feed.status}"
                    )

                    # Increment processing attempts
                    feed.processing_attempts += 1
                    db.session.commit()

                    process_start = time.time()
                    parsed_feed = feedparser.parse(feed.url)
                    parse_time = time.time() - process_start
                    logger.info(f"Feed parsing completed in {parse_time:.2f}s")

                    if hasattr(parsed_feed.feed, 'title'):
                        feed.title = parsed_feed.feed.title[:
                                                            200]  # Truncate feed title
                    else:
                        feed.title = urlparse(
                            feed.url).netloc[:200]  # Truncate netloc

                    feed.last_checked = datetime.utcnow()

                    # Get the user object for customized summary generation
                    user = User.query.get(feed.user_id)
                    if not user:
                        continue

                    # Register webhook only if not already registered and not webhook triggered
                    if not webhook_triggered and callback_url:
                        try:
                            if feed.webhook_id:
                                logger.info(
                                    f"Webhook already registered for feed {feed.url} with ID: {feed.webhook_id}"
                                )
                            else:
                                # First, explicitly rollback any pending transactions to avoid cascading errors
                                db.session.rollback()
                                
                                # Check if this webhook ID already exists for another feed with the same URL
                                existing_feed = Feed.query.filter(
                                    Feed.webhook_id.isnot(None),
                                    Feed.id != feed.id,
                                    Feed.url == feed.url
                                ).first()
                                
                                if existing_feed:
                                    try:
                                        # Reuse the existing webhook ID for the same feed URL
                                        logger.info(f"Reusing existing webhook ID {existing_feed.webhook_id} for feed URL {feed.url}")
                                        feed.webhook_id = existing_feed.webhook_id
                                        db.session.commit()
                                    except Exception as commit_error:
                                        logger.error(f"Failed to set webhook ID (reuse): {str(commit_error)}")
                                        db.session.rollback()
                                        # Skip webhook registration for this feed to avoid further errors
                                        continue
                                else:
                                    try:
                                        # Register a new webhook - first check if any other feed with same URL has webhook
                                        existing_webhook = db.session.query(Feed.webhook_id).filter(
                                            Feed.webhook_id.isnot(None),
                                            Feed.url == feed.url
                                        ).first()
                                        
                                        if existing_webhook:
                                            # Another check to see if since our earlier check, a webhook was registered
                                            feed.webhook_id = existing_webhook[0]
                                            db.session.commit()
                                            logger.info(f"Using existing webhook ID {feed.webhook_id} for feed URL {feed.url}")
                                        else:
                                            # Register a new webhook
                                            webhook_response = register_webhook(feed.url, callback_url)
                                            if webhook_response and 'subscriptionId' in webhook_response:
                                                feed.webhook_id = webhook_response['subscriptionId']
                                                try:
                                                    db.session.commit()
                                                    logger.info(
                                                        f"Registered webhook for feed {feed.url} with ID: {feed.webhook_id}"
                                                    )
                                                except Exception as commit_error:
                                                    logger.error(f"Failed to save webhook ID: {str(commit_error)}")
                                                    db.session.rollback()
                                                    # Don't set webhook_id to avoid future duplicate key errors
                                                    feed.webhook_id = None
                                    except Exception as webhook_error:
                                        logger.error(f"Error during webhook handling: {str(webhook_error)}")
                                        db.session.rollback()
                        except Exception as e:
                            logger.error(
                                f"Failed to register webhook for feed {feed.url}: {str(e)}"
                            )
                            # Continue processing even if webhook registration fails

                    # Process entries (limited to 10)
                    entries = parsed_feed.entries[:10]
                    processed_count = 0

                    for entry in entries:
                        try:
                            existing = Article.query.filter_by(
                                url=entry.link, feed_id=feed.id).first()

                            if not existing:
                                published = entry.get('published_parsed', None)
                                if published:
                                    published = datetime(*published[:6])

                                article = Article(
                                    title=entry.title[:200] if entry.title else
                                    '',  # Truncate to 200 chars
                                    url=entry.link,
                                    content=entry.get('description', ''),
                                    published_date=published,
                                    feed_id=feed.id)

                                summary_result = generate_summary(
                                    entry.title, entry.get('description', ''),
                                    user)

                                if summary_result:
                                    article.summary = summary_result['summary']
                                    article.critique = summary_result.get(
                                        'critique')

                                    # Process tags
                                    if 'tags' in summary_result:
                                        for tag_name in summary_result['tags']:
                                            tag = get_or_create_tag(tag_name)
                                            article.tags.append(tag)

                                    # Process categories
                                    if 'categories' in summary_result:
                                        for category_name in summary_result[
                                                'categories']:
                                            category = get_or_create_category(
                                                category_name)
                                            article.categories.append(category)

                                    article.processed = True
                                    processed_count += 1

                                db.session.add(article)
                                db.session.commit()
                                logger.info(
                                    f"Added new article: {article.title}")

                        except Exception as e:
                            logger.error(f"Error processing entry: {str(e)}")
                            continue

                    # Update feed status and metrics
                    feed = Feed.query.get(feed_id)
                    if feed:
                        end_time = time.time()
                        processing_duration = end_time - start_time

                        feed.status = 'active'
                        feed.error_message = None
                        feed.success_count += 1
                        feed.last_successful_process = datetime.utcnow()

                        # Update processing metrics
                        feed.total_articles_processed += processed_count
                        feed.last_processing_duration = processing_duration

                        # Calculate average processing time
                        if feed.average_processing_time == 0:
                            feed.average_processing_time = processing_duration
                        else:
                            feed.average_processing_time = (
                                feed.average_processing_time +
                                processing_duration) / 2

                        # Calculate health score (0-100) based on success rate
                        total_attempts = feed.success_count + feed.failure_count
                        if total_attempts > 0:
                            feed.health_score = (feed.success_count /
                                                 total_attempts) * 100

                        db.session.commit()
                        logger.info(
                            f"Feed {feed.url} marked as active (processed {processed_count} articles in {processing_duration:.2f}s)"
                        )

                except Exception as e:
                    logger.error(f"Error processing feed {feed_id}: {str(e)}")
                    feed = Feed.query.get(feed_id)
                    if feed:
                        end_time = time.time()
                        processing_duration = end_time - start_time

                        feed.status = 'error'
                        feed.error_message = str(e)
                        feed.failure_count += 1
                        feed.last_failed_process = datetime.utcnow()
                        feed.last_processing_duration = processing_duration

                        # Update health score on failure
                        total_attempts = feed.success_count + feed.failure_count
                        if total_attempts > 0:
                            feed.health_score = (feed.success_count /
                                                 total_attempts) * 100

                        # Calculate next retry time with exponential backoff
                        retry_delay = min(2**(feed.processing_attempts - 1) *
                                          300, 3600)  # Max 1 hour delay
                        next_retry = datetime.utcnow() + timedelta(
                            seconds=retry_delay)

                        if feed.processing_attempts >= 3:  # Max retries reached
                            feed.status = 'error'
                            logger.warning(
                                f"Feed {feed_id} has reached maximum retry attempts"
                            )
                        else:
                            # Schedule retry with exponential backoff
                            scheduler.add_job(func=schedule_feed_processing,
                                              args=[feed_id],
                                              trigger='date',
                                              run_date=next_retry,
                                              id=f'retry_feed_{feed_id}',
                                              replace_existing=True,
                                              misfire_grace_time=300)
                            logger.info(
                                f"Scheduled retry for feed {feed_id} at {next_retry}"
                            )

                        db.session.commit()
                    continue

            logger.info("Feed processing complete.")

        except Exception as e:
            logger.error(f"Error in process_feeds: {str(e)}")
            raise


def schedule_feed_processing(feed_id):
    """Schedule processing of a specific feed, respecting the hourly limit."""
    from app import app, db

    def process_with_context():
        with app.app_context():
            # Check if feed can be processed (hasn't been checked in the last hour)
            feed = Feed.query.get(feed_id)
            if feed:
                one_hour_ago = datetime.utcnow() - timedelta(hours=1)
                can_process = (feed.last_checked is None or feed.last_checked < one_hour_ago)
                
                if can_process:
                    logger.info(f"Processing feed ID {feed_id} as scheduled")
                    process_feeds([feed])
                else:
                    next_available = feed.last_checked + timedelta(hours=1)
                    time_until = (next_available - datetime.utcnow()).total_seconds() / 60
                    logger.info(f"Feed ID {feed_id} was checked recently. Next available in {time_until:.1f} minutes")
                    
                    # Reschedule for the next available time
                    scheduler.add_job(
                        func=schedule_feed_processing,
                        args=[feed_id],
                        trigger='date',
                        run_date=next_available,
                        id=f'process_feed_{feed_id}',
                        replace_existing=True,
                        misfire_grace_time=900)

    job_id = f'process_feed_{feed_id}'
    try:
        scheduler.remove_job(job_id)
    except:
        pass

    # Add new job
    scheduler.add_job(
        func=process_with_context,
        id=job_id,
        next_run_time=datetime.now(),
        misfire_grace_time=900,  # 15 minutes grace time
        coalesce=True,
        max_instances=1)
    logger.info(f"Scheduled processing for feed ID: {feed_id}")


def schedule_tasks():
    """Schedule periodic tasks for feed processing and email digests."""
    from app import app, scheduler

    def process_with_context():
        with app.app_context():
            try:
                logger.info("Starting scheduled feed processing...")
                start_time = datetime.now()

                # Check and clean any stale jobs before processing
                if hasattr(scheduler, 'cleanup_stale_jobs'):
                    scheduler.cleanup_stale_jobs()

                process_feeds()
                duration = (datetime.now() - start_time).total_seconds()
                logger.info(
                    f"Completed feed processing in {duration:.2f} seconds")
                return duration
            except Exception as e:
                logger.error(f"Error in scheduled feed processing: {str(e)}")
                raise

    try:
        # Remove any existing jobs before scheduling new ones
        existing_jobs = {job.id: job for job in scheduler.get_jobs()}
        logger.info(f"Found existing jobs: {list(existing_jobs.keys())}")

        # Define job configurations with improved settings
        jobs_config = [
            {
                'id': 'process_feeds',
                'func': process_with_context,
                'trigger': 'interval',
                'minutes': 60,
                'next_run_time': datetime.now() + timedelta(seconds=30),
                'misfire_grace_time': 1800,  # 30 minutes grace time
                'max_instances': 3,  # Allow multiple instances
                'coalesce': True,
                'description': 'Feed processing task'
            },
            {
                'id': 'send_daily_digest',
                'func': send_daily_digest_with_context,
                'trigger': 'cron',
                'hour': 0,
                'minute': 0,
                'misfire_grace_time': 3600,
                'max_instances': 1,
                'coalesce': True,
                'description': 'Daily digest email task'
            },
            {
                'id': 'send_weekly_digest',
                'func': send_weekly_digest_with_context,
                'trigger': 'cron',
                'day_of_week': 'sun',
                'hour': 0,
                'minute': 0,
                'misfire_grace_time': 3600,
                'max_instances': 1,
                'coalesce': True,
                'description': 'Weekly digest email task'
            },
            {
                'id': 'cleanup_expired_accounts',
                'func': cleanup_expired_accounts_with_context,
                'trigger': 'interval',
                'hours': 6,
                'next_run_time': datetime.now() + timedelta(minutes=5),
                'misfire_grace_time': 1800,
                'max_instances': 1,
                'coalesce': True,
                'description': 'Expired accounts cleanup task'
            }
        ]

        # Schedule or update jobs
        for config in jobs_config:
            job_id = config.pop('id')
            description = config.pop('description')

            try:
                if job_id in existing_jobs:
                    logger.info(
                        f"Updating existing job: {job_id} ({description})")
                    # Remove old job before adding new one
                    scheduler.remove_job(job_id)

                logger.info(f"Scheduling job: {job_id} ({description})")
                scheduler.add_job(**config, id=job_id, replace_existing=True)
            except Exception as e:
                logger.error(
                    f"Failed to schedule job {job_id} ({description}): {str(e)}"
                )
                continue

        # Verify scheduled jobs
        jobs = scheduler.get_jobs()
        logger.info(f"Total scheduled jobs: {len(jobs)}")
        for job in jobs:
            logger.info(f"Job ID: {job.id}\n"
                        f"  Next run: {job.next_run_time}\n"
                        f"  Max instances: {job.max_instances}\n"
                        f"  Misfire grace time: {job.misfire_grace_time}")

    except Exception as e:
        logger.error(f"Error scheduling tasks: {str(e)}")
        raise


def send_daily_digest_with_context():
    from app import app  # Import app inside function to avoid circular import issues
    
    with app.app_context():
        try:
            logger.info("Starting daily digest email send...")
            start_time = datetime.now()
            send_daily_digest()
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"Completed daily digest in {duration:.2f} seconds")
        except Exception as e:
            logger.error(f"Error sending daily digest: {str(e)}")
            raise


def send_weekly_digest_with_context():
    from app import app  # Import app inside function to avoid circular import issues
    
    with app.app_context():
        try:
            logger.info("Starting weekly digest email send...")
            start_time = datetime.now()
            send_weekly_digest()
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"Completed weekly digest in {duration:.2f} seconds")
        except Exception as e:
            logger.error(f"Error sending weekly digest: {str(e)}")
            raise


def cleanup_expired_accounts_with_context():
    from app import app  # Import app here to avoid circular imports

    with app.app_context():
        try:
            logger.info("Starting expired accounts cleanup...")
            start_time = datetime.now()
            cleanup_expired_accounts()
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"Completed expired accounts cleanup in {duration:.2f} seconds"
            )
        except Exception as e:
            logger.error(f"Error cleaning up expired accounts: {str(e)}")
            raise
