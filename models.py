from datetime import datetime
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    feeds = db.relationship('Feed', backref='user', lazy=True)
    
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

class Feed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    title = db.Column(db.String(200))
    last_checked = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')  # pending, active, error
    error_message = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    articles = db.relationship('Article', backref='feed', lazy=True, cascade='all, delete-orphan')

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
