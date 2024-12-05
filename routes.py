from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app import app, db
from models import User, Feed, Article, Tag, Category
from feed_processor import schedule_feed_processing
from datetime import datetime
from sqlalchemy import or_, desc, nullslast
from urllib.parse import urlparse
from werkzeug.security import generate_password_hash
from markdown import markdown
import bleach
from email_service import send_verification_email
import logging
import requests
import os
import feedparser
import opml
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

def verify_recaptcha(token):
    try:
        if not token:
            logger.warning("No reCAPTCHA token provided")
            return False

        logger.debug(f"Verifying reCAPTCHA token: {token[:10]}...")  # Log first 10 chars of token for debugging
        
        verify_url = 'https://www.google.com/recaptcha/api/siteverify'
        payload = {
            'secret': os.environ.get('RECAPTCHA_SECRET_KEY'),
            'response': token,
            'remoteip': request.remote_addr
        }
        
        logger.debug(f"Sending verification request to {verify_url}")
        logger.debug(f"Request payload: secret=<redacted>, response length={len(token)}, remoteip={request.remote_addr}")
        
        response = requests.post(verify_url, data=payload)
        
        logger.debug(f"reCAPTCHA API response status: {response.status_code}")
        result = response.json()
        logger.info(f"reCAPTCHA verification full response: {result}")
        
        if not result.get('success'):
            error_codes = result.get('error-codes', [])
            logger.warning(f"reCAPTCHA verification failed with error codes: {error_codes}")
            return False
            
        # Log the full verification details
        logger.info(f"reCAPTCHA verification details: score={result.get('score')}, action={result.get('action')}, timestamp={result.get('challenge_ts')}")
        
        if result.get('action') != 'register':
            logger.warning(f"reCAPTCHA action mismatch. Expected 'register', got: {result.get('action')}")
            return False
            
        score = result.get('score', 0)
        logger.info(f"reCAPTCopHA score: {score}")
        
        if score < 0.5:
            logger.warning(f"reCAPTCHA score too low: {score}")
            return False
            
        logger.info("reCAPTCHA verification successful")
        return True
        
    except Exception as e:
        logger.error(f"Error verifying reCAPTCHA: {str(e)}", exc_info=True)
        return False

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
        try:
            recaptcha_token = request.form.get('recaptcha_token')
            if not recaptcha_token:
                flash('Please ensure JavaScript is enabled for reCAPTCHA validation')
                return redirect(url_for('register'))
                
            if not verify_recaptcha(recaptcha_token):
                flash('reCAPTCHA verification failed. Please try again')
                return redirect(url_for('register'))
            
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
            logger.info(f"Generating verification token for user {user.username}")
            token = user.generate_verification_token()
            
            db.session.add(user)
            db.session.commit()
            logger.info(f"User {user.username} added to database with token: {token[:10]}...")
            
            # Send verification email
            logger.info(f"Sending verification email to {user.email}")
            if send_verification_email(user, token):
                logger.info("Verification email sent successfully")
                flash('Registration successful! Please check your email to verify your account.')
            else:
                logger.error("Failed to send verification email")
                flash('Registration successful but there was an error sending the verification email. Please contact support.')
            
            return redirect(url_for('login'))
            
        except Exception as e:
            logger.error(f"Registration error: {str(e)}")
            flash('An error occurred during registration. Please try again')
            return redirect(url_for('register'))
            
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

@app.route('/resend-verification', methods=['GET', 'POST'])
def resend_verification():
    if request.method == 'POST':
        email = request.form.get('email')
        if not email:
            flash('Please provide an email address.')
            return redirect(url_for('resend_verification'))
            
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('No account found with that email address.')
            return redirect(url_for('resend_verification'))
            
        if user.email_verified:
            flash('This email address is already verified.')
            return redirect(url_for('login'))
            
        token = user.generate_verification_token()
        db.session.commit()
        
        if send_verification_email(user, token):
            flash('Verification email sent! Please check your inbox.')
        else:
            flash('Error sending verification email. Please try again later.')
        
        return redirect(url_for('login'))
        
    return render_template('resend_verification.html')

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

@app.route('/change-password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if not current_password or not new_password or not confirm_password:
        flash('All password fields are required')
        return redirect(url_for('settings'))
        
    if not current_user.check_password(current_password):
        flash('Current password is incorrect')
        return redirect(url_for('settings'))
        
    if new_password != confirm_password:
        flash('New passwords do not match')
        return redirect(url_for('settings'))
        
    if len(new_password) < 8:
        flash('New password must be at least 8 characters long')
        return redirect(url_for('settings'))
        
    current_user.set_password(new_password)
    db.session.commit()
    
    flash('Password changed successfully')
    return redirect(url_for('settings'))

@app.route('/dashboard')
@login_required
def dashboard():
    feeds = Feed.query.filter_by(user_id=current_user.id).all()
    recent_articles = Article.query.join(Feed).filter(
        Feed.user_id == current_user.id
    ).order_by(nullslast(desc(Article.published_date))).limit(10).all()
    
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
            title=title[:200] if title else urlparse(feed_url).netloc[:200],  # Truncate to 200 chars
            user_id=current_user.id
        )
        db.session.add(new_feed)
        db.session.commit()
        
        schedule_feed_processing(new_feed.id)
        flash('Feed added successfully. Processing will begin shortly.')
        return redirect(url_for('manage_feeds'))
    
    feeds = Feed.query.filter_by(user_id=current_user.id).all()
    return render_template('feed_manage.html', feeds=feeds)


@app.route('/feeds/health')
@login_required
def feed_health_dashboard():
    # Get all feeds for the current user
    feeds = Feed.query.filter_by(user_id=current_user.id).all()
    
    # Calculate overall statistics
    total_feeds = len(feeds)
    active_feeds = sum(1 for feed in feeds if feed.status == 'active')
    error_feeds = sum(1 for feed in feeds if feed.status == 'error')
    total_articles = sum(feed.total_articles_processed or 0 for feed in feeds)
    
    return render_template('health_dashboard.html',
                         feeds=feeds,
                         total_feeds=total_feeds,
                         active_feeds=active_feeds,
                         error_feeds=error_feeds,
                         total_articles=total_articles)

@app.route('/feeds/import-opml', methods=['POST'])
@login_required
def import_opml():
    if 'opml_file' not in request.files:
        flash('No file provided')
        return redirect(url_for('manage_feeds'))
    
    file = request.files['opml_file']
    if file.filename == '':
        flash('No file selected')
        return redirect(url_for('manage_feeds'))
        
    if not file.filename.endswith(('.opml', '.xml')):
        flash('Invalid file type. Please upload an OPML file')
        return redirect(url_for('manage_feeds'))
    
    try:
        # Parse OPML content
        outline = opml.parse(file)
        imported_count = 0
        skipped_count = 0
        
        def process_outline(outline):
            nonlocal imported_count, skipped_count
            
            # Process current level
            for entry in outline:
                # Check if entry has xmlUrl (RSS feed)
                if hasattr(entry, 'xmlUrl'):
                    # Check if feed already exists
                    existing_feed = Feed.query.filter_by(
                        url=entry.xmlUrl,
                        user_id=current_user.id
                    ).first()
                    
                    if not existing_feed:
                        new_feed = Feed(
                            url=entry.xmlUrl,
                            title=(getattr(entry, 'text', '') or getattr(entry, 'title', ''))[:200],  # Truncate to 200 chars
                            user_id=current_user.id
                        )
                        db.session.add(new_feed)
                        imported_count += 1
                    else:
                        skipped_count += 1
                
                # Process nested outlines (if any exist)
                if len(entry) > 0:  # Using Python sequence operator to check for nested elements
                    process_outline(entry)  # Recursively process nested outlines
        
        # Process the OPML file
        process_outline(outline)
        
        # Commit all new feeds
        db.session.commit()
        
        # Schedule processing for all new feeds
        feeds = Feed.query.filter_by(user_id=current_user.id).all()
        for feed in feeds:
            schedule_feed_processing(feed.id)
        
        flash(f'Successfully imported {imported_count} feeds ({skipped_count} skipped as duplicates)')
        
    except Exception as e:
        logger.error(f"Error importing OPML file: {str(e)}")
        flash('Error importing OPML file. Please ensure the file is valid')
        
    return redirect(url_for('manage_feeds'))

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
    
    # Order by published date, handling null values
    query = query.order_by(nullslast(desc(Article.published_date)))
    
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