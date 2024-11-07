from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app import app, db
from models import User, Feed, Article
from feed_processor import schedule_feed_processing
from datetime import datetime
import feedparser
from urllib.parse import urlparse
from werkzeug.security import generate_password_hash

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        if User.query.filter_by(username=request.form['username']).first():
            flash('Username already exists')
            return redirect(url_for('register'))
        
        user = User(
            username=request.form['username'],
            email=request.form['email']
        )
        user.set_password(request.form['password'])
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for('dashboard'))
    return render_template('register.html')

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        current_user.email_notifications_enabled = 'email_notifications_enabled' in request.form
        current_user.email_frequency = request.form['email_frequency']
        db.session.commit()
        flash('Settings updated successfully')
        return redirect(url_for('settings'))
    return render_template('settings.html')

@app.route('/dashboard')
@login_required
def dashboard():
    feeds = Feed.query.filter_by(user_id=current_user.id).all()
    recent_articles = Article.query.join(Feed).filter(
        Feed.user_id == current_user.id
    ).order_by(Article.created_at.desc()).limit(10).all()
    return render_template('dashboard.html', feeds=feeds, articles=recent_articles)

@app.route('/feeds', methods=['GET', 'POST'])
@login_required
def manage_feeds():
    if request.method == 'POST':
        feed_url = request.form['url']
        # Try to get feed title immediately
        parsed = feedparser.parse(feed_url)
        title = parsed.feed.get('title', urlparse(feed_url).netloc)
        
        new_feed = Feed(
            url=feed_url,
            title=title,  # Set initial title
            user_id=current_user.id
        )
        db.session.add(new_feed)
        db.session.commit()
        
        # Schedule async processing of the new feed
        schedule_feed_processing(new_feed.id)
        flash('Feed added successfully. Processing will begin shortly.')
        return redirect(url_for('manage_feeds'))
    
    feeds = Feed.query.filter_by(user_id=current_user.id).all()
    return render_template('feed_manage.html', feeds=feeds)

@app.route('/feeds/<int:feed_id>/delete', methods=['POST'])
@login_required
def delete_feed(feed_id):
    feed = Feed.query.get_or_404(feed_id)
    if feed.user_id != current_user.id:
        flash('Unauthorized')
        return redirect(url_for('manage_feeds'))
    
    db.session.delete(feed)
    db.session.commit()
    return redirect(url_for('manage_feeds'))

@app.route('/summaries')
@login_required
def summaries():
    articles = Article.query.join(Feed).filter(
        Feed.user_id == current_user.id,
        Article.processed == True
    ).order_by(Article.created_at.desc()).all()
    return render_template('summaries.html', articles=articles)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))
