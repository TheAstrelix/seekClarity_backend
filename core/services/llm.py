# services/llm_service.py

import requests
from django.conf import settings

API_KEY = settings.MISTRAL_API_KEY
API_URL = settings.MISTRAL_API_URL


# ==============================
# 🔹 CORE LLM CALL
# ==============================

def call_llm(prompt, max_tokens=500, temperature=0.3):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "open-mixtral-8x7b",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": temperature
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()

        return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    except Exception as e:
        return f"Error: {str(e)}"


# ==============================
# 🔹 PROMPT BUILDERS
# ==============================

def build_summary_prompt(content, page_number=None, previous_content=None, forward_content=None):
    page_context = f"from page {page_number}" if page_number else ""

    previous_context = f"\nPrevious page context:\n{previous_content}\n" if previous_content else ""
    forward_context = f"\nNext page context:\n{forward_content}\n" if forward_content else ""

    return f"""
Summarize the following content {page_context}.

{previous_context}
{forward_context}

Rules:
- Keep it concise
- Focus on key ideas
- No extra explanation

Content:
{content}
"""


def build_qa_prompt(content, query, page_number=None, previous_content=None, forward_content=None):
    page_context = f" from page {page_number}" if page_number else ""

    previous_context = f"\nPrevious context:\n{previous_content}\n" if previous_content else ""
    forward_context = f"\nNext context:\n{forward_content}\n" if forward_content else ""

    return f"""
Answer the question using ONLY the provided content{page_context}.

{previous_context}
{forward_context}

Rules:
- Give a direct answer
- If answer exists, extract it clearly
- If not found, say: "Not found in content"
- Keep it short
- No extra explanation
- Plain text only

Question:
{query}

Content:
{content}
"""


def build_question_prompt(content, page_number=None):
    page_context = f"based on page {page_number}" if page_number else ""

    return f"""
Generate 2-3 important study questions {page_context}.

Rules:
- Each question on one line
- Mix factual + conceptual
- Simple plain text
- No extra explanation

Content:
{content}
"""


def build_intent_prompt(query):
    return f"""
Classify the query into one of these:
summary | generate_questions | question

Query: {query}

Return only one word.
"""


def build_followup_prompt(current_query, last_query):
    return f"""
Determine whether the current query is a follow-up question.

Previous message:
{last_query}

Current message:
{current_query}

If it depends on previous context → YES
Else → NO

Only return YES or NO.
"""


# ==============================
# 🔹 HELPERS
# ==============================

def get_content(msg):
    if msg.selected_text:
        return msg.selected_text

    if msg.page and msg.page.text_content:
        return msg.page.text_content

    return msg.content


def get_page_context(msg):
    page_number = msg.page.page_number if msg.page else None

    previous_content = None
    forward_content = None

    if msg.page and page_number:
        try:
            prev_page = msg.page.document.pages.filter(page_number=page_number - 1).first()
            if prev_page:
                previous_content = prev_page.text_content
        except:
            pass

        try:
            next_page = msg.page.document.pages.filter(page_number=page_number + 1).first()
            if next_page:
                forward_content = next_page.text_content
        except:
            pass

    return page_number, previous_content, forward_content


# ==============================
# 🔹 AGENTS
# ==============================

def summary_agent(msg):
    content = get_content(msg)
    page_number, prev, next_ = get_page_context(msg)

    prompt = build_summary_prompt(content, page_number, prev, next_)
    return call_llm(prompt)


def question_agent(msg):
    content = get_content(msg)
    page_number = msg.page.page_number if msg.page else None

    prompt = build_question_prompt(content, page_number)
    return call_llm(prompt)


def qa_agent(msg, is_follow_up):
    content = get_content(msg)
    page_number, prev, next_ = get_page_context(msg)

    if is_follow_up:
        query = f"""
This is a follow-up question. Use previous context properly.

{msg.content}
"""
    else:
        query = msg.content

    prompt = build_qa_prompt(content, query, page_number, prev, next_)
    return call_llm(prompt)


# ==============================
# 🔹 INTENT DETECTION
# ==============================

def detect_intent(msg):
    if msg.intent:
        return msg.intent

    prompt = build_intent_prompt(msg.content)
    intent = call_llm(prompt).strip().lower()

    allowed = ["summary", "generate_questions", "question"]

    return intent if intent in allowed else "question"


# ==============================
# 🔹 FOLLOW-UP DETECTION
# ==============================

def detect_follow_up_llm(msg, last_msg):
    if not last_msg:
        return False

    prompt = build_followup_prompt(msg.content, last_msg.content)
    result = call_llm(prompt).strip().upper()

    return result == "YES"