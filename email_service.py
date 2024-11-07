from flask import render_template
from flask_mail import Message
from app import mail, db
from models import User, Article, Feed
from datetime import datetime, timedelta

def send_daily_digest():
    users = User.query.all()
    
    for user in users:
        # Get articles from the last 24 hours
        yesterday = datetime.utcnow() - timedelta(days=1)
        articles = Article.query.join(Feed).filter(
            Feed.user_id == user.id,
            Article.created_at >= yesterday,
            Article.processed == True
        ).all()
        
        if articles:
            try:
                msg = Message(
                    subject="Your Daily RSS Feed Digest",
                    recipients=[user.email],
                    html=render_template(
                        'email/daily_digest.html',
                        user=user,
                        articles=articles
                    )
                )
                mail.send(msg)
            except Exception as e:
                print(f"Error sending email to {user.email}: {str(e)}")
