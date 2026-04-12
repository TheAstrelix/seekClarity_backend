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

        # ✅ Safe parsing
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    except Exception as e:
        return f"Error: {str(e)}"


# ==============================
# 🔹 PROMPT BUILDERS
# ==============================

def build_summary_prompt(content, page_number=None, previous_content=None):
    page_context = f"from page {page_number}" if page_number else ""
    previous_context = ""
    if previous_content:
        previous_context = f"""
Previous page context:
{previous_content}

---

"""
    
    return f"""
Summarize the following content {page_context}.

Requirements:
- Provide 4-5 sentences (detailed but focused)
- Include all key concepts and main ideas
- Use simple, clear language
- Use **bold** for important terms and concepts
- NO preamble like "Here's a summary:" or "Here's the content:"
- NO introductory phrases
- Go directly into the content
- NO separators like "---"

{previous_context}Current page content:
{content}
"""


def build_highlight_prompt(content, page_number=None):
    page_context = f"from page {page_number}" if page_number else ""
    return f"""
Extract the most important highlights and key points {page_context}.

Requirements:
- Return 3-5 bullet points maximum
- Only the most critical information
- Keep each point to one line
- Format as markdown bullet list (- for bullets)
- Use **bold** for key terms and concepts
- NO preamble or introductory text
- Go directly to bullet points
- NO separators like "---"

Content:
{content}
"""


def build_question_prompt(content, page_number=None):
    page_context = f"based on page {page_number}" if page_number else ""
    return f"""
Generate 2-3 important study questions {page_context}.

Requirements:
- Questions should test understanding of key concepts
- Format as numbered markdown list (1. 2. 3.)
- Each question on one line
- Mix of factual and analytical questions
- Use **bold** for important terms
- NO preamble or explanatory text before questions
- Go directly to questions
- NO separators like "---"

Content:
{content}
"""


def build_rag_prompt(context, question):
    return f"""
    You are a helpful assistant.

    Use ONLY the provided context to answer the question.
    If the answer is not in the context, say "Not found in document".

    Context:
    {context}

    Question:
    {question}
    """


def build_intent_prompt(query):
    return f"""
    Classify the query into one of these:
    summary | highlight | generate_questions | question

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
    """
    Get content for LLM processing.
    Priority:
    1. Selected text (highlight intent)
    2. Page text content (summary/highlight/question on page)
    3. User message content (fallback)
    """
    if msg.selected_text:
        return msg.selected_text

    if msg.page and msg.page.text_content:
        return msg.page.text_content

    return msg.content


# ==============================
# 🔹 AGENTS (LLM POWERED)
# ==============================

def summary_agent(msg):
    content = get_content(msg)
    page_number = msg.page.page_number if msg.page else None
    
    # 🔥 Get previous page content if exists
    previous_content = None
    if msg.page and page_number and page_number > 1:
        try:
            previous_page = msg.page.document.pages.filter(page_number=page_number - 1).first()
            if previous_page and previous_page.text_content:
                previous_content = previous_page.text_content
        except:
            pass
    
    prompt = build_summary_prompt(content, page_number, previous_content)
    return call_llm(prompt)


def highlight_agent(msg):
    content = get_content(msg)
    page_number = msg.page.page_number if msg.page else None
    prompt = build_highlight_prompt(content, page_number)
    return call_llm(prompt)


def question_agent(msg):
    content = get_content(msg)
    page_number = msg.page.page_number if msg.page else None
    prompt = build_question_prompt(content, page_number)
    return call_llm(prompt)


def rag_agent(msg, is_follow_up):
    context = get_content(msg)

    # ✅ Use follow-up info
    if is_follow_up:
        question = f"""
        This is a follow-up question. Use previous context to answer properly.

        Question: {msg.content}
        """
    else:
        question = msg.content

    prompt = build_rag_prompt(
        context=context,
        question=question
    )

    return call_llm(prompt)


# ==============================
# 🔹 INTENT DETECTION (LLM)
# ==============================

def detect_intent(msg):
    if msg.intent:
        return msg.intent

    prompt = build_intent_prompt(msg.content)
    intent = call_llm(prompt).strip().lower()

    allowed = ["summary", "highlight", "generate_questions", "question"]

    return intent if intent in allowed else "question"


# ==============================
# 🔹 FOLLOW-UP DETECTION (LLM)
# ==============================

def detect_follow_up_llm(msg, last_msg):
    if not last_msg:
        return False

    prompt = build_followup_prompt(
        current_query=msg.content,
        last_query=last_msg.content
    )

    result = call_llm(prompt).strip().upper()

    return result == "YES"