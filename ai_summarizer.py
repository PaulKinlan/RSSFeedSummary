import os
import google.generativeai as genai
from typing import Optional, Dict

# Configure Gemini API
genai.configure(api_key=os.environ['GOOGLE_GEMINI_API_KEY'])
model = genai.GenerativeModel('gemini-pro')

def generate_summary(title: str, content: str) -> Optional[Dict[str, str]]:
    try:
        # Prepare the prompt
        prompt = f"""
        Article Title: {title}
        Content: {content}
        
        Please provide:
        1. A concise summary of the main points (max 3 sentences)
        2. A brief critique of the content, considering:
           - Objectivity
           - Supporting evidence
           - Potential biases
        
        Format the response as:
        Summary: [summary text]
        Critique: [critique text]
        """
        
        response = model.generate_content(prompt)
        response_text = response.text
        
        # Parse the response
        parts = response_text.split('Critique:')
        summary = parts[0].replace('Summary:', '').strip()
        critique = parts[1].strip() if len(parts) > 1 else "No critique available"
        
        return {
            'summary': summary,
            'critique': critique
        }
    except Exception as e:
        print(f"Error generating summary: {str(e)}")
        return None
