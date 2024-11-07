from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app import app, db
from models import User, Feed, Article, Tag, Category
from feed_processor import schedule_feed_processing
from datetime import datetime
from sqlalchemy import or_
import feedparser
from urllib.parse import urlparse
from werkzeug.security import generate_password_hash
from markdown import markdown
import bleach
from email_service import send_verification_email

def convert_markdown_to_html(text):
    # Convert markdown to HTML and sanitize
    allowed_tags = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'em', 
                   'ul', 'ol', 'li', 'code', 'pre', 'blockquote']
    allowed_attributes = {'*': ['class']}
    
    html = markdown(text)
    clean_html = bleach.clean(html, tags=allowed_tags, attributes=allowed_attributes)
    return clean_html

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
            if not user.email_verified:
                flash('Please verify your email address before logging in.')
                return redirect(url_for('login'))
            
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
        
        if User.query.filter_by(email=request.form['email']).first():
            flash('Email already registered')
            return redirect(url_for('register'))
        
        user = User(
            username=request.form['username'],
            email=request.form['email'],
            email_verified=False
        )
        user.set_password(request.form['password'])
        
        # Generate verification token
        token = user.generate_verification_token()
        
        db.session.add(user)
        db.session.commit()
        
        # Send verification email
        if send_verification_email(user, token):
            flash('Registration successful! Please check your email to verify your account.')
        else:
            flash('Registration successful but there was an error sending the verification email. Please contact support.')
        
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/verify-email/<token>')
def verify_email(token):
    user = User.query.filter_by(verification_token=token).first()
    
    if not user:
        flash('Invalid verification link')
        return redirect(url_for('login'))
    
    if datetime.utcnow() > user.verification_token_expires:
        flash('Verification link has expired. Please request a new one.')
        return redirect(url_for('login'))
    
    user.email_verified = True
    user.verification_token = None
    user.verification_token_expires = None
    db.session.commit()
    
    flash('Email verified successfully! You can now log in.')
    return redirect(url_for('login'))

@app.route('/resend-verification')
@login_required
def resend_verification():
    if current_user.email_verified:
        return redirect(url_for('dashboard'))
    
    token = current_user.generate_verification_token()
    db.session.commit()
    
    if send_verification_email(current_user, token):
        flash('Verification email sent! Please check your inbox.')
    else:
        flash('Error sending verification email. Please try again later.')
    
    return redirect(url_for('login'))

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        # Update email notification settings
        current_user.email_notifications_enabled = 'email_notifications_enabled' in request.form
        current_user.email_frequency = request.form['email_frequency']
        
        # Update summarization preferences
        current_user.summary_length = request.form['summary_length']
        current_user.include_critique = 'include_critique' in request.form
        current_user.focus_areas = request.form['focus_areas']
        
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
    
    for article in recent_articles:
        if article.summary:
            article.summary = convert_markdown_to_html(article.summary)
    
    return render_template('dashboard.html', feeds=feeds, articles=recent_articles)

@app.route('/feeds', methods=['GET', 'POST'])
@login_required
def manage_feeds():
    if request.method == 'POST':
        feed_url = request.form['url']
        parsed = feedparser.parse(feed_url)
        title = parsed.feed.get('title', urlparse(feed_url).netloc)
        
        new_feed = Feed(
            url=feed_url,
            title=title,
            user_id=current_user.id
        )
        db.session.add(new_feed)
        db.session.commit()
        
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
    page = request.args.get('page', 1, type=int)
    per_page = 10
    search_query = request.args.get('q', '')
    filter_type = request.args.get('filter', 'all')
    
    # Base query
    query = Article.query.join(Feed).filter(Feed.user_id == current_user.id)
    
    # Apply search if provided
    if search_query:
        if filter_type == 'title':
            query = query.filter(Article.title.ilike(f'%{search_query}%'))
        elif filter_type == 'summary':
            query = query.filter(Article.summary.ilike(f'%{search_query}%'))
        elif filter_type == 'tags':
            query = query.join(Article.tags).filter(Tag.name.ilike(f'%{search_query}%'))
        else:  # 'all'
            query = query.outerjoin(Article.tags).outerjoin(Article.categories).filter(
                or_(
                    Article.title.ilike(f'%{search_query}%'),
                    Article.summary.ilike(f'%{search_query}%'),
                    Tag.name.ilike(f'%{search_query}%'),
                    Category.name.ilike(f'%{search_query}%')
                )
            ).distinct()
    
    # Order by most recent first
    query = query.order_by(Article.created_at.desc())
    
    # Paginate results
    articles = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Convert markdown to HTML for summaries and critiques
    for article in articles.items:
        if article.summary:
            article.summary = convert_markdown_to_html(article.summary)
        if article.critique:
            article.critique = convert_markdown_to_html(article.critique)
    
    return render_template('summaries.html', articles=articles)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))