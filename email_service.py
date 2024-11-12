import os
import resend
import logging
from flask import render_template, current_app
from app import db
from models import User, Article, Feed
from datetime import datetime, timedelta

# Configure Resend and logging
resend.api_key = os.environ.get('RESEND_API_KEY')
logger = logging.getLogger(__name__)

def send_email_for_user(user, subject, html_content):
    try:
        params = {
            "from": "rss@tldr.express",
            "to": [user.email],
            "subject": subject,
            "html": html_content
        }
        
        logger.info(f"Sending email to {user.email}")
        response = resend.Emails.send(params)
        
        # Resend API returns a dictionary with 'id' on success
        if isinstance(response, dict) and 'id' in response:
            logger.info(f"Email sent successfully to {user.email} (ID: {response['id']})")
            return True
        else:
            logger.warning(f"Unexpected response format from Resend API: {response}")
            return False
            
    except Exception as e:
        logger.error(f"Error sending email to {user.email}: {str(e)}")
        return False

def send_verification_email(user, token):
    try:
        logger.info(f"Preparing verification email for {user.email}")
        with current_app.test_request_context():
            html_content = render_template(
                'email/verify_email.html',
                user=user,
                token=token
            )
        
        result = send_email_for_user(
            user,
            "Verify Your Email Address - RSS Monitor",
            html_content
        )
        
        if result:
            logger.info(f"Verification email sent successfully to {user.email}")
            return True
        else:
            logger.warning(f"Could not send verification email to {user.email}")
            return False
            
    except Exception as e:
        logger.error(f"Error preparing verification email: {str(e)}")
        return False

def send_daily_digest():
    """Send daily digest emails to users who have enabled them"""
    users = User.query.filter_by(
        email_notifications_enabled=True,
        email_frequency='daily',
        email_verified=True  # Only send to verified users
    ).all()
    
    for user in users:
        # Get articles from the last 24 hours
        yesterday = datetime.utcnow() - timedelta(days=1)
        articles = Article.query.join(Feed).filter(
            Feed.user_id == user.id,
            Article.created_at >= yesterday,
            Article.processed == True
        ).order_by(Article.published_date.desc().nullslast()).all()
        
        if articles:
            try:
                with current_app.test_request_context():
                    html_content = render_template(
                        'email/daily_digest.html',
                        user=user,
                        articles=articles
                    )
                
                if send_email_for_user(
                    user,
                    "Your Daily RSS Feed Digest",
                    html_content
                ):
                    logger.info(f"Daily digest sent successfully to {user.email}")
                else:
                    logger.warning(f"Failed to send daily digest to {user.email}")
            except Exception as e:
                logger.error(f"Error preparing daily digest for {user.email}: {str(e)}")

def send_weekly_digest():
    """Send weekly digest emails to users who have enabled them"""
    users = User.query.filter_by(
        email_notifications_enabled=True,
        email_frequency='weekly',
        email_verified=True  # Only send to verified users
    ).all()
    
    for user in users:
        # Get articles from the last 7 days
        last_week = datetime.utcnow() - timedelta(days=7)
        articles = Article.query.join(Feed).filter(
            Feed.user_id == user.id,
            Article.created_at >= last_week,
            Article.processed == True
        ).order_by(Article.published_date.desc().nullslast()).all()
        
        if articles:
            try:
                with current_app.test_request_context():
                    html_content = render_template(
                        'email/daily_digest.html',  # We can reuse the same template
                        user=user,
                        articles=articles
                    )
                
                if send_email_for_user(
                    user,
                    "Your Weekly RSS Feed Digest",
                    html_content
                ):
                    logger.info(f"Weekly digest sent successfully to {user.email}")
                else:
                    logger.warning(f"Failed to send weekly digest to {user.email}")
            except Exception as e:
                logger.error(f"Error preparing weekly digest for {user.email}: {str(e)}")
