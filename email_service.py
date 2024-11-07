import os
import resend
from flask import render_template
from app import db
from models import User, Article, Feed
from datetime import datetime, timedelta

# Configure Resend
resend.api_key = os.environ.get('RESEND_API_KEY')

def send_email_for_user(user, subject, html_content):
    """Send email using Resend API"""
    try:
        params = {
            "from": "RSS Monitor <rss@tldr.express>",
            "to": [user.email],
            "subject": subject,
            "html": html_content
        }
        
        response = resend.Emails.send(params)
        return True if response.id else False
    except Exception as e:
        print(f"Error sending email to {user.email}: {str(e)}")
        return False

def send_verification_email(user, token):
    """Send email verification link to user"""
    html_content = render_template(
        'email/verify_email.html',
        user=user,
        token=token
    )
    
    return send_email_for_user(
        user,
        "Verify Your Email Address - RSS Monitor",
        html_content
    )

def send_daily_digest():
    """Send daily digest emails to users who have enabled them"""
    users = User.query.filter_by(
        email_notifications_enabled=True,
        email_frequency='daily'
    ).all()
    
    for user in users:
        # Get articles from the last 24 hours
        yesterday = datetime.utcnow() - timedelta(days=1)
        articles = Article.query.join(Feed).filter(
            Feed.user_id == user.id,
            Article.created_at >= yesterday,
            Article.processed == True
        ).all()
        
        if articles:
            html_content = render_template(
                'email/daily_digest.html',
                user=user,
                articles=articles
            )
            
            send_email_for_user(
                user,
                "Your Daily RSS Feed Digest",
                html_content
            )

def send_weekly_digest():
    """Send weekly digest emails to users who have enabled them"""
    users = User.query.filter_by(
        email_notifications_enabled=True,
        email_frequency='weekly'
    ).all()
    
    for user in users:
        # Get articles from the last 7 days
        last_week = datetime.utcnow() - timedelta(days=7)
        articles = Article.query.join(Feed).filter(
            Feed.user_id == user.id,
            Article.created_at >= last_week,
            Article.processed == True
        ).all()
        
        if articles:
            html_content = render_template(
                'email/daily_digest.html',  # We can reuse the same template
                user=user,
                articles=articles
            )
            
            send_email_for_user(
                user,
                "Your Weekly RSS Feed Digest",
                html_content
            )