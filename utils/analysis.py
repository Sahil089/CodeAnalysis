import os
from typing import List, TypedDict
import google.generativeai as genai
from dotenv import load_dotenv
from pathlib import Path
import json

# Load environment variables from .env file
load_dotenv()

# Retrieve the API key from the environment
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')

# Configure genai with the API key
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
else:
    raise ValueError("GOOGLE_API_KEY is not set in the environment variables.")

class Recipe(TypedDict):
    file_name: str
    file_score: int
    file_analysis: str
    suggestion: str
    vulnerable_lines: List[str]

def get_file_content(file_path):
    """Attempt to read and return file content; skip unreadable files."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except Exception:
        return None

import json

def analyze_file(file_path: str, content: str) -> Recipe:
    model = genai.GenerativeModel("gemini-1.5-flash")
    
    prompt = f"""
Analyze the following code and provide a security assessment in JSON format:

{content}

Response must be valid JSON with exactly this structure:
{{
    "file_name": "{file_path}",
    "file_score": <number 0-10>,
    "file_analysis": "<detailed analysis of the code's security implications, minimum 50 words>",
    "suggestion": "<specific, actionable security improvements, minimum 30 words>",
    "vulnerable_lines": [
        "line 1 with vulnerability",
        "line 2 with vulnerability",
        ...
    ]
}}

For file_score:
- 0-3: Critical security issues
- 4-6: Moderate security concerns
- 7-8: Minor security concerns
- 9-10: Generally secure

The file_analysis must include:
- Main purpose of the code
- Security implications
- Potential vulnerabilities
- Current security measures

The suggestion must include:
- Specific code improvements
- Security best practices
- Priority fixes needed

If no vulnerable lines are found, use ["No vulnerable lines"]

Response must be valid JSON that can be parsed using json.loads().
"""
    
    try:
        result = model.generate_content(prompt)
        
        if not result or not hasattr(result, 'text'):
            return create_error_response(file_path)

        # Clean and parse the response
        response_text = result.text.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:-3]
        elif response_text.startswith('{'):
            response_text = response_text

        try:
            parsed_result = json.loads(response_text)
            
            # Ensure all required fields are present with proper content
            file_name = parsed_result.get("file_name", file_path)
            file_score = int(parsed_result.get("file_score", 0))
            file_analysis = parsed_result.get("file_analysis", "").strip() or "Analysis not available."
            suggestion = parsed_result.get("suggestion", "").strip() or "No suggestions available."
            vulnerable_lines = parsed_result.get("vulnerable_lines", ["No vulnerable lines"])
            
            # Index the vulnerable lines if they are not "No vulnerable lines"
            indexed_vulnerable_lines = [
                {"index": i + 1, "line": line} for i, line in enumerate(vulnerable_lines) 
                if line != "No vulnerable lines"
            ] if vulnerable_lines != ["No vulnerable lines"] else [{"index": 0, "line": "No vulnerable lines"}]
            
            structured_result = Recipe(
                file_name=file_name,
                file_score=file_score,
                file_analysis=file_analysis,
                suggestion=suggestion,
                vulnerable_lines=indexed_vulnerable_lines
            )
            
            return structured_result

        except json.JSONDecodeError:
            print(f"Failed to parse JSON for {file_path}")
            return create_error_response(file_path)
            
    except Exception as e:
        print(f"Error analyzing {file_path}: {str(e)}")
        return create_error_response(file_path)

def create_error_response(file_path: str) -> Recipe:
    """Create a standard error response."""
    return Recipe(
        file_name=file_path,
        file_score=0,
        file_analysis="Analysis failed due to an error.",
        suggestion="Suggestion generation failed.",
        vulnerable_lines=["No vulnerable lines"]
    )

def scan_directory(directory):
    """Recursively scan directory and analyze all files."""
    results = []
    excluded_dirs = {'.git', '__pycache__', 'node_modules', 'venv'}
    
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in excluded_dirs]
        
        for file in files:
            file_path = Path(root) / file
            content = get_file_content(file_path)
            if content:
                analysis = analyze_file(str(file_path), content)
                if analysis:
                    results.append(analysis)
    
    return {
        "repository": f"file://{directory}",
        "scan_results": results
    }
