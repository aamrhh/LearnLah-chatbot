from flask import Flask, render_template, request, jsonify
import google.generativeai as genai
from datetime import date
from dotenv import load_dotenv
import os

app = Flask(__name__)

# API Key — loaded from .env file
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

# Bot personality
system_prompt = """
You are LearnLah Bot, a personal Malay language companion.
You understand English, Malay, and Manglish.
Always respond in English unless the user asks in Malay.

Your job is to:
1. Tell the meaning of Malay words in English
2. Give synonyms and antonyms of Malay words
3. Show how to use a Malay word in a sentence
4. Chat with users to help them practice Malay

Rules:
- Keep responses short and easy to understand
- Always give examples when explaining words
- Be friendly and encouraging
- Always check and correct spelling mistakes in Malay words
- Follow Kamus Dewan Bahasa dan Pustaka (DBP) standards
- If user asks something not related to Malay, politely redirect them
"""

chat_history = []
learned_words = []
quiz_state = {
    "active": False,
    "questions": [],
    "current_q": 0,
    "answers": [],
    "correct_answers": ""
}

def chat_with_bot(user_input):
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash-lite",
        system_instruction=system_prompt
    )
    chat = model.start_chat(history=chat_history)
    response = chat.send_message(user_input)
    chat_history.append({"role": "user", "parts": [user_input]})
    chat_history.append({"role": "model", "parts": [response.text]})
    return response.text.strip()

def extract_malay_word(user_input, bot_response):
    text = user_input.lower()
    trigger_phrases = ["meaning of", "maksud", "synonym for", "synonym of",
                       "antonym for", "antonym of", "sentence for", "use"]
    for phrase in trigger_phrases:
        if phrase in text:
            after = text.split(phrase, 1)[1].strip()
            word = after.split()[0].strip("?'\".,!") if after.split() else None
            if word:
                return word
    return None

def get_word_of_the_day():
    today = date.today().strftime("%d %B %Y")
    prompt = f"""Today is {today}.
    Pick ONE interesting Malay word as the Word of the Day.
    Do NOT add any introductory sentence. Start directly with Word:

    Word: [the word]
    Meaning: [meaning in English]
    Example: [one sentence in Malay] ([English translation])
    Synonym: [one synonym in Malay]
    Antonym: [one antonym in Malay, or None if not applicable]
    Memory Tip: [a fun short tip to remember this word]"""
    model = genai.GenerativeModel(model_name="gemini-2.5-flash-lite")
    response = model.generate_content(prompt)
    return response.text.strip()

def start_quiz():
    if len(learned_words) >= 3:
        word_list = ", ".join(learned_words[-10:])
        word_instruction = f"Pick 3 words from this list the user has learned: {word_list}"
    else:
        word_instruction = "Pick 3 interesting Malay words from your knowledge (DBP standards)"

    quiz_prompt = f"""You are quizzing a user who is learning Malay.
    {word_instruction}
    Rules: Must be real DBP Malay words. Mix difficulty. Avoid basic words.

    Format EXACTLY like this, no extra text before Question 1:

    Question 1: What is the meaning of '[word]'?
    A) [option]
    B) [option]
    C) [option]
    D) [option]

    Question 2: Fill in the blank: '[Malay sentence with blank]'
    A) [option]
    B) [option]
    C) [option]
    D) [option]

    Question 3: Which word is a synonym of '[word]'?
    A) [option]
    B) [option]
    C) [option]
    D) [option]

    ANSWERS: Q1=[answer], Q2=[answer], Q3=[answer]"""

    quiz_content = chat_with_bot(quiz_prompt)

    if "ANSWERS:" in quiz_content:
        questions_part, answers_part = quiz_content.split("ANSWERS:", 1)
    else:
        questions_part = quiz_content
        answers_part = ""

    raw_questions = questions_part.strip().split("Question")
    questions_list = ["Question" + q for q in raw_questions if q.strip() != ""]

    quiz_state["active"] = True
    quiz_state["questions"] = questions_list
    quiz_state["current_q"] = 0
    quiz_state["answers"] = []
    quiz_state["correct_answers"] = answers_part.strip()

    return questions_list[0] if questions_list else "Quiz could not be generated. Try again!"

def submit_quiz_answer(user_answer):
    quiz_state["answers"].append(user_answer.strip().upper())
    quiz_state["current_q"] += 1

    if quiz_state["current_q"] < 3:
        return quiz_state["questions"][quiz_state["current_q"]]
    else:
        quiz_state["active"] = False
        score_prompt = f"""The user just completed a Malay quiz.
        Their answers: Q1={quiz_state['answers'][0]}, Q2={quiz_state['answers'][1]}, Q3={quiz_state['answers'][2]}.
        Correct answers: {quiz_state['correct_answers']}
        Calculate score out of 3. Tell which were correct/wrong.
        Give encouraging message: 3/3 excellent, 2/3 good job, 1/3 or 0/3 don't give up!
        Keep it short and friendly!"""
        return chat_with_bot(score_prompt)

@app.route("/")
def home():
    wotd = get_word_of_the_day()
    today = date.today().strftime("%d %B %Y")
    wotd_word = extract_malay_word("word of the day", wotd)
    if wotd_word and wotd_word not in learned_words:
        learned_words.append(wotd_word)
    return render_template("index.html", wotd=wotd, today=today)

@app.route("/chat", methods=["POST"])
def chat():
    user_input = request.json.get("message")

    # Handle special commands
    if user_input.lower() == "wotd":
        wotd = get_word_of_the_day()
        return jsonify({"response": f"🌅 Today's Word of the Day:\n\n{wotd}"})

    if user_input.lower() == "help":
        return jsonify({"response": """Here's what you can do! 🌟
- Type any Malay word → I'll explain it
- wotd → Show today's Word of the Day again
- quiz → Test yourself on words you've learned
- help → Show this message"""})

    # Handle quiz
    if quiz_state["active"]:
        response = submit_quiz_answer(user_input)
        return jsonify({"response": response})

    if "quiz" in user_input.lower():
        first_question = start_quiz()
        return jsonify({"response": "🎯 QUIZ TIME! Let's test your Malay knowledge!\n\n" + first_question})

    # Normal chat
    response = chat_with_bot(user_input)

    # Track learned words
    detected_word = extract_malay_word(user_input, response)
    if detected_word and detected_word not in learned_words:
        learned_words.append(detected_word)

    return jsonify({"response": response})

if __name__ == "__main__":
    app.run(debug=True)