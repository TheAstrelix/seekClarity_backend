import json
import re

def build_prompt_for_ats(resume, jd):
    return f"""
You are an advanced ATS (Applicant Tracking System).

Your task is to compare a RESUME with a JOB DESCRIPTION and evaluate how well they match.

### Instructions:
- Be strict and realistic like a real ATS.
- Focus on skills, experience, keywords, and relevance.
- Do NOT hallucinate.
- Do NOT add explanations outside JSON.

### Output Format (STRICT JSON ONLY):
{{
  "score": number (0-100),
  "matched_keywords": ["..."],
  "missing_keywords": ["..."],
  "suggestions": ["..."]
}}

### Job Description:
{jd}

### Resume:
{resume}
"""



def parse_llm_response(response_text):
    try:
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print("Parsing error:", e)

    return {
        "score": 0,
        "matched_keywords": [],
        "missing_keywords": [],
        "suggestions": ["Parsing failed"]
    }