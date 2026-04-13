# tasks.py

from celery import shared_task
from core.models import ChatMessage

from core.services.llm import (
    summary_agent,
    build_qa_prompt,
    question_agent,
    rag_agent,
    detect_intent,
    detect_follow_up_llm   # 🔥 NEW
)


# ==============================
# 🔹 MAIN TASK
# ==============================

@shared_task(bind=True, queue="chat_processing")
def process_chat_message(self, message_id):

    msg = ChatMessage.objects.get(id=message_id)
    chat = msg.chat

    try:
        # 🔹 STEP 1: CONTEXT
        last_msg = ChatMessage.objects.filter(chat=chat).exclude(id=msg.id).last()

        # 🔹 STEP 2: DECISION (LLM POWERED 🔥)
        is_follow_up = detect_follow_up_llm(msg, last_msg)
        intent = detect_intent(msg)

        # 🔹 STEP 3: ROUTING
        if intent == "summary":
            answer = summary_agent(msg)

        elif intent == "highlight":
            answer = build_qa_prompt(msg)

        elif intent == "generate_questions":
            answer = question_agent(msg)

        else:
            answer = rag_agent(msg, is_follow_up)

        # 🔹 STEP 4: SAVE RESPONSE
        ChatMessage.objects.create(
            chat=chat,
            role="assistant",
            content=answer,
            parent=msg,
            status="done"
        )

        msg.status = "done"
        msg.save()

    except Exception as e:
        msg.status = "failed"
        msg.error = str(e)
        msg.save()
        raise e