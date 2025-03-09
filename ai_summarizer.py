import os
import google.generativeai as genai
import logging
from typing import Optional, Dict
from models import User, Tag, Category, db

# Configure logging and Gemini API
logger = logging.getLogger(__name__)
genai.configure(api_key=os.environ['GOOGLE_GEMINI_API_KEY'])
model = genai.GenerativeModel('gemini-2.0-flash')


def get_or_create_tag(name: str) -> Optional[Tag]:
    """Get existing tag or create a new one with proper validation"""
    # Clean and validate tag name
    cleaned_name = Tag.clean_tag_name(name)
    if not cleaned_name:
        return None

    tag = Tag.query.filter_by(name=cleaned_name).first()
    if not tag:
        tag = Tag(name=cleaned_name)
        db.session.add(tag)
    return tag


def get_or_create_category(name: str,
                           description: str = None) -> Optional[Category]:
    """Get existing category or create a new one with proper validation"""
    if not name:
        return None

    # Clean and truncate category name
    cleaned_name = name.lower().strip(
    )[:50]  # Truncate to match database column length

    try:
        category = Category.query.filter_by(name=cleaned_name).first()
        if not category:
            category = Category(name=cleaned_name, description=description)
            db.session.add(category)
        return category
    except Exception as e:
        logger.error(f"Error creating category '{cleaned_name}': {str(e)}")
        return None


def generate_summary(title: str, content: str,
                     user: User) -> Optional[Dict[str, str]]:
    try:
        # Determine summary length based on user preference
        length_guide = {
            'short': '1-2 sentences',
            'medium': '3-4 sentences',
            'long': '5-6 sentences'
        }.get(user.summary_length, '3-4 sentences')

        # Construct focus areas from user preferences
        focus_areas = user.focus_areas.split(',') if user.focus_areas else [
            'main points', 'key findings'
        ]
        focus_areas_str = '\n'.join(f'   - {area.strip()}'
                                    for area in focus_areas)

        # Prepare the prompt for summary, critique, tags, and categories
        prompt = f"""
        Article Title: {title}
        Content: {content}
        
        Please provide:
        1. A {length_guide} summary focusing on:
{focus_areas_str}

        2. Generate up to 5 relevant tags (single words or short phrases, each max 30 characters) that best describe the content
        
        3. Categorize the content into 1-2 broad categories from this list:
           - Technology
           - Business
           - Science
           - Health
           - Politics
           - Culture
           - Education
           - Environment
           
        Format the response as:
        Summary: [summary text]
        Tags: [comma-separated tags]
        Categories: [comma-separated categories]
        """

        if user.include_critique:
            prompt += "\nCritique: [critique analyzing objectivity, evidence, and potential biases]"

        response = model.generate_content(prompt)
        response_text = response.text

        # Parse the response
        parts = {}
        current_section = None

        for line in response_text.split('\n'):
            line = line.strip()
            if line:
                if line.startswith('Summary:'):
                    current_section = 'summary'
                    parts[current_section] = line.replace('Summary:',
                                                          '').strip()
                elif line.startswith('Tags:'):
                    current_section = 'tags'
                    # Clean and validate tags
                    tags = [
                        tag.strip()
                        for tag in line.replace('Tags:', '').strip().split(',')
                    ]
                    parts[current_section] = [
                        tag for tag in tags if Tag.clean_tag_name(tag)
                    ]
                elif line.startswith('Categories:'):
                    current_section = 'categories'
                    categories = [
                        cat.strip() for cat in line.replace(
                            'Categories:', '').strip().split(',')
                    ]
                    # Only keep valid category names
                    parts[current_section] = [
                        cat for cat in categories if cat and len(cat) <= 50
                    ]
                elif line.startswith('Critique:'):
                    current_section = 'critique'
                    parts[current_section] = line.replace('Critique:',
                                                          '').strip()
                elif current_section:
                    parts[current_section] = parts.get(current_section,
                                                       '') + ' ' + line

        return {
            'summary': parts.get('summary', ''),
            'critique':
            parts.get('critique') if user.include_critique else None,
            'tags': parts.get('tags', []),
            'categories': parts.get('categories', [])
        }

    except Exception as e:
        logger.error(f"Error generating summary: {str(e)}")
        return None
