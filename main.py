import streamlit as st
import requests
import io
from pypdf import PdfReader

st.set_page_config(page_title="AI Agent + Document", layout="wide")

# ====== МОДЕЛИ ======
AVAILABLE_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "groq/compound",
    "groq/compound-mini",
    "openai/gpt-oss-safeguard-20b",
]
MODEL_DISPLAY_NAMES = {
    "openai/gpt-oss-120b": "GPT-oss-120b (мощная)",
    "openai/gpt-oss-20b": "GPT-oss-20b (быстрая)",
    "groq/compound": "Groq Compound",
    "groq/compound-mini": "Groq Compound Mini",
    "openai/gpt-oss-safeguard-20b": "GPT-OSS Safeguard",
}

# Сколько символов документа подмешивать в system-prompt
DOC_CONTEXT_LIMIT = 6000


# ====== GROQ ======
def chat_with_groq(api_key, model, messages, system_prompt="", temperature=0.7):
    payload = []
    if system_prompt:
        payload.append({"role": "system", "content": system_prompt})
    payload.extend(messages)

    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        json={"model": model, "messages": payload,
              "temperature": temperature, "max_tokens": 3000},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


# ====== PDF ======
def extract_pdf_text(file_bytes: bytes) -> tuple[str, int]:
    """Возвращает (текст, кол-во страниц)."""
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            txt = page.extract_text() or ""
        except Exception as e:
            txt = f"[Ошибка извлечения стр. {i}: {e}]"
        if txt.strip():
            pages.append(f"--- стр. {i} ---\n{txt}")
    return "\n\n".join(pages), len(reader.pages)


# ====== SESSION STATE ======
if "messages" not in st.session_state:
    st.session_state.messages = []
if "doc_text" not in st.session_state:
    st.session_state.doc_text = ""
if "doc_name" not in st.session_state:
    st.session_state.doc_name = "—"
if "doc_pages" not in st.session_state:
    st.session_state.doc_pages = 0

# ====== САЙДБАР ======
with st.sidebar:
    st.header("⚙️ Настройки")

    try:
        default_key = st.secrets["GROQ_API_KEY"]
    except Exception:
        default_key = ""

    api_key = st.text_input("🔑 Groq API Key", value=default_key,
                            type="password",
                            help="https://console.groq.com")

    model = st.selectbox(
        "🤖 Модель",
        options=AVAILABLE_MODELS,
        format_func=lambda x: MODEL_DISPLAY_NAMES.get(x, x),
        index=0,
    )

    system_prompt = st.text_area(
        "🧠 System prompt",
        value="Ты — ассистент. Отвечай кратко и по делу. "
              "Если есть документ — опирайся на него.",
        height=120,
    )

    st.divider()
    st.caption(f"📄 Документ: **{st.session_state.doc_name}**")
    st.caption(f"Страниц: {st.session_state.doc_pages} · "
               f"символов: {len(st.session_state.doc_text):,}")

    if st.button("🗑 Очистить чат", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

if not api_key:
    st.warning("⚠️ Введите Groq API Key в сайдбаре. "
               "[Получить бесплатно](https://console.groq.com)")
    st.stop()

# ====== МАКЕТ ======
left, right = st.columns([1, 1.4], gap="large")

# ---------- ЧАТ ----------
with left:
    st.subheader("💬 Чат с ИИ-агентом")

    chat_box = st.container(height=520)
    with chat_box:
        for m in st.session_state.messages:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

    prompt = st.chat_input("Введите сообщение...")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with chat_box:
            with st.chat_message("user"):
                st.markdown(prompt)

        ctx = ""
        if st.session_state.doc_text:
            ctx = (f"\n\n=== ДОКУМЕНТ ({st.session_state.doc_name}) ===\n"
                   f"{st.session_state.doc_text[:DOC_CONTEXT_LIMIT]}")

        with chat_box:
            with st.chat_message("assistant"):
                with st.spinner("Думаю..."):
                    try:
                        reply = chat_with_groq(
                            api_key, model,
                            st.session_state.messages,
                            system_prompt=system_prompt + ctx,
                        )
                    except Exception as e:
                        reply = f"❌ Ошибка: {e}"
                st.markdown(reply)

        st.session_state.messages.append(
            {"role": "assistant", "content": reply})
        st.rerun()

# ---------- ДОКУМЕНТ ----------
with right:
    st.subheader("📄 Документ")

    uploaded = st.file_uploader(
        "Открыть файл",
        type=["txt", "md", "py", "json", "csv", "log", "pdf"],
    )

    if uploaded is not None:
        try:
            if uploaded.name.lower().endswith(".pdf"):
                text, pages = extract_pdf_text(uploaded.read())
                st.session_state.doc_text = text
                st.session_state.doc_name = uploaded.name
                st.session_state.doc_pages = pages
                if not text.strip():
                    st.warning("⚠️ В PDF нет извлекаемого текста "
                               "(возможно, это сканы — нужен OCR).")
            else:
                st.session_state.doc_text = uploaded.read().decode(
                    "utf-8", errors="replace")
                st.session_state.doc_name = uploaded.name
                st.session_state.doc_pages = 0
        except Exception as e:
            st.error(f"Ошибка чтения: {e}")

    st.caption(
        f"Файл: **{st.session_state.doc_name}** · "
        f"{len(st.session_state.doc_text):,} символов"
        + (f" · {st.session_state.doc_pages} стр."
           if st.session_state.doc_pages else "")
    )

    edit_mode = st.toggle("Редактировать", value=False)
    if edit_mode:
        st.session_state.doc_text = st.text_area(
            "Содержимое", value=st.session_state.doc_text, height=480)
    else:
        st.text_area(
            "Содержимое", value=st.session_state.doc_text,
            height=480, disabled=True)