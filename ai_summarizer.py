import os
import google.generativeai as genai
from typing import Optional, Dict
from models import User

# Configure Gemini API
genai.configure(api_key=os.environ['GOOGLE_GEMINI_API_KEY'])
model = genai.GenerativeModel('gemini-pro')

def generate_summary(title: str, content: str, user: User) -> Optional[Dict[str, str]]:
    try:
        # Determine summary length based on user preference
        length_guide = {
            'short': '1-2 sentences',
            'medium': '3-4 sentences',
            'long': '5-6 sentences'
        }.get(user.summary_length, '3-4 sentences')
        
        # Construct focus areas from user preferences
        focus_areas = user.focus_areas.split(',') if user.focus_areas else ['main points', 'key findings']
        focus_areas_str = '\n'.join(f'   - {area.strip()}' for area in focus_areas)
        
        # Prepare the prompt
        prompt = f"""
        Article Title: {title}
        Content: {content}
        
        Please provide:
        1. A {length_guide} summary focusing on:
{focus_areas_str}
        """
        
        if user.include_critique:
            prompt += """
        2. A brief critique of the content, considering:
           - Objectivity
           - Supporting evidence
           - Potential biases
        
        Format the response as:
        Summary: [summary text]
        Critique: [critique text]
        """
        else:
            prompt += "\nFormat the response as:\nSummary: [summary text]"
        
        response = model.generate_content(prompt)
        response_text = response.text
        
        # Parse the response
        if user.include_critique:
            parts = response_text.split('Critique:')
            summary = parts[0].replace('Summary:', '').strip()
            critique = parts[1].strip() if len(parts) > 1 else "No critique available"
            
            return {
                'summary': summary,
                'critique': critique
            }
        else:
            summary = response_text.replace('Summary:', '').strip()
            return {
                'summary': summary,
                'critique': None
            }
            
    except Exception as e:
        print(f"Error generating summary: {str(e)}")
        return None
