from datetime import datetime, timedelta
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import secrets

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    feeds = db.relationship('Feed', backref='user', lazy=True)
    
    # Email verification fields
    email_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(100), unique=True)
    verification_token_expires = db.Column(db.DateTime)
    
    # Email notification settings
    email_notifications_enabled = db.Column(db.Boolean, default=True)
    email_frequency = db.Column(db.String(10), default='daily')  # daily, weekly, never
    
    # Summarization preferences
    summary_length = db.Column(db.String(10), default='medium')  # short, medium, long
    include_critique = db.Column(db.Boolean, default=True)
    focus_areas = db.Column(db.String(200), default='main points, key findings')  # comma-separated focus areas
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def generate_verification_token(self):
        self.verification_token = secrets.token_urlsafe(32)
        self.verification_token_expires = datetime.utcnow() + timedelta(hours=24)
        return self.verification_token

class Feed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    title = db.Column(db.String(200))
    last_checked = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')  # pending, active, error
    error_message = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    articles = db.relationship('Article', backref='feed', lazy=True, cascade='all, delete-orphan')
    
    # Feed processing status tracking
    processing_attempts = db.Column(db.Integer, default=0)
    last_successful_process = db.Column(db.DateTime)
    last_failed_process = db.Column(db.DateTime)
    success_count = db.Column(db.Integer, default=0)
    failure_count = db.Column(db.Integer, default=0)

# Association tables for many-to-many relationships
article_tags = db.Table('article_tags',
    db.Column('article_id', db.Integer, db.ForeignKey('article.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True)
)

article_categories = db.Table('article_categories',
    db.Column('article_id', db.Integer, db.ForeignKey('article.id'), primary_key=True),
    db.Column('category_id', db.Integer, db.ForeignKey('category.id'), primary_key=True)
)

class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)  # Reduced from 50 to 30 for better manageability
    articles = db.relationship('Article', secondary=article_tags, backref=db.backref('tags', lazy='dynamic'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    @staticmethod
    def clean_tag_name(name):
        """Clean and validate tag name"""
        if not name:
            return None
        # Remove extra whitespace and convert to lowercase
        cleaned = ' '.join(name.lower().split()).strip()
        # Truncate if longer than 30 characters
        return cleaned[:30] if cleaned else None

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))
    articles = db.relationship('Article', secondary=article_categories, backref=db.backref('categories', lazy='dynamic'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    published_date = db.Column(db.DateTime)
    content = db.Column(db.Text)
    summary = db.Column(db.Text)
    critique = db.Column(db.Text)
    processed = db.Column(db.Boolean, default=False)
    feed_id = db.Column(db.Integer, db.ForeignKey('feed.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
