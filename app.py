import streamlit as st
from datetime import datetime
import os
import json
import tempfile
import re
import random

# =========================
# RE:Bloom 개인 기억 전화부스 웹 프로토타입
# =========================
# 실행 명령어:
# py -m streamlit run app.py
#
# 설치 명령어:
# py -m pip install streamlit openai python-dotenv openai-whisper
#
# 방향:
# - 한 사람 전용 기억 전화부스
# - 기억을 남기면 자동으로 번호와 추억 이름이 생성됨
# - 추억 이름을 사용자가 직접 입력할 수도 있음
# - 전화번호부에는 번호 + 추억 이름만 표시
# - 번호를 입력하면 해당 기억이 사진/음성/자막처럼 재생되는 느낌

try:
    from openai import OpenAI
    from dotenv import load_dotenv

    load_dotenv()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception:
    client = None

try:
    import whisper
except Exception:
    whisper = None

MEMORY_DIR = "personal_memories"
MEDIA_DIR = "personal_media"
os.makedirs(MEMORY_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)

st.set_page_config(
    page_title="RE:Bloom 기억 전화부스",
    page_icon="☎️",
    layout="wide"
)

# -------------------------
# 디자인
# -------------------------
st.markdown("""
<style>
    .main-title {
        font-size: 48px;
        font-weight: 900;
        text-align: center;
        color: #2b2b2b;
        margin-bottom: 5px;
    }
    .sub-title {
        font-size: 20px;
        text-align: center;
        color: #666;
        margin-bottom: 28px;
    }
    .phone-box {
        background: linear-gradient(135deg, #fff7ed 0%, #fffdf8 100%);
        border: 2px solid #e8cfc2;
        border-radius: 28px;
        padding: 28px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.06);
        margin-bottom: 18px;
    }
    .screen-box {
        background-color: #242424;
        color: #fff6e8;
        border-radius: 24px;
        padding: 28px;
        margin-bottom: 18px;
        border: 5px solid #3b3b3b;
    }
    .memory-card {
        background-color: #ffffff;
        border-radius: 22px;
        padding: 24px;
        border: 1px solid #dedede;
        box-shadow: 0 4px 14px rgba(0,0,0,0.04);
        margin-top: 16px;
    }
    .phonebook-row {
        background-color: #fffdf7;
        border: 1px solid #e3d5c7;
        border-radius: 14px;
        padding: 15px 18px;
        margin: 8px 0;
        font-size: 21px;
        font-weight: 700;
    }
    .big-caption {
        font-size: 25px;
        line-height: 1.6;
        font-weight: 700;
        color: #333;
        background-color: #fff8e8;
        border-left: 8px solid #d9a16f;
        padding: 20px;
        border-radius: 14px;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">☎️ RE:Bloom 기억 전화부스</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">번호를 누르면 나의 추억이 다시 연결됩니다.</div>', unsafe_allow_html=True)

# -------------------------
# 기본 함수
# -------------------------
def sanitize_filename(value):
    return re.sub(r"[^가-힣a-zA-Z0-9_\-]", "_", value)


def load_memories():
    memories = []
    for filename in os.listdir(MEMORY_DIR):
        if filename.endswith(".json"):
            path = os.path.join(MEMORY_DIR, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    memories.append(json.load(f))
            except Exception:
                pass
    memories.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return memories


def make_memory_code():
    existing_codes = {m.get("code") for m in load_memories()}
    while True:
        code = str(random.randint(1000, 9999))
        if code not in existing_codes:
            return code


def save_memory(memory):
    filename = f"{memory['code']}_{sanitize_filename(memory['title'])}.json"
    path = os.path.join(MEMORY_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def find_memory_by_code(code):
    for memory in load_memories():
        if memory.get("code") == code:
            return memory
    return None


def save_uploaded_file(uploaded_file, code, label):
    if uploaded_file is None:
        return ""
    ext = os.path.splitext(uploaded_file.name)[1]
    filename = f"{code}_{label}{ext}"
    path = os.path.join(MEDIA_DIR, filename)
    with open(path, "wb") as f:
        f.write(uploaded_file.read())
    return filename


def media_path(filename):
    if not filename:
        return None
    path = os.path.join(MEDIA_DIR, filename)
    return path if os.path.exists(path) else None

# -------------------------
# Whisper 음성 변환
# -------------------------
@st.cache_resource
def load_whisper_model():
    if whisper is None:
        return None
    return whisper.load_model("base")


def transcribe_audio(uploaded_audio):
    model = load_whisper_model()
    if model is None:
        return None, "Whisper가 설치되어 있지 않습니다. py -m pip install openai-whisper 를 실행해주세요."

    suffix = os.path.splitext(uploaded_audio.name)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
        tmp_file.write(uploaded_audio.read())
        tmp_path = tmp_file.name

    try:
        result = model.transcribe(tmp_path, language="ko")
        return result["text"].strip(), None
    except Exception as e:
        return None, str(e)
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

# -------------------------
# AI 정리
# -------------------------
def fallback_classify(story):
    return {
        "title": "오늘의 기억",
        "summary": "사용자가 남긴 개인적인 기억을 정리한 기록입니다.",
        "caption": story[:160] if story else "기억이 기록되었습니다.",
        "question": "이 기억에서 가장 선명하게 남아 있는 장면은 무엇인가요?",
        "message": "이 기억은 시간이 지나도 다시 꺼내볼 수 있는 소중한 기록입니다."
    }


def ai_classify_memory(story):
    if client is None:
        return fallback_classify(story)

    prompt = f"""
다음 개인 기억을 정리해줘.
원본을 과장하거나 꾸미지 말고, 사용자가 말한 내용 기반으로만 정리해.
아래 JSON 형식으로만 답해줘. 설명 문장 금지.

[원본 기억]
{story}

필드:
- title: 전화번호부에 들어갈 짧은 추억 이름. 예) 어린 시절의 여름, 아버지와 걷던 밤, 처음 서울에 간 날
- summary: 2~3문장 요약
- caption: 재생 화면에 큰 자막으로 보여줄 핵심 문장 2~3문장
- question: 다음에 이어서 물어볼 회상 질문 1개
- message: 가족에게 남길 수 있는 짧은 메시지 2~3문장
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 원본 기억을 존중하고 왜곡하지 않는 기억 정리 도우미다."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4
        )
        text = response.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception:
        return fallback_classify(story)

# -------------------------
# 기억 재생 화면
# -------------------------
def render_memory_player(memory):
    st.markdown('<div class="screen-box">', unsafe_allow_html=True)
    st.markdown(f"## ☎️ {memory.get('code')} 연결됨")
    st.markdown(f"### {memory.get('title')}")
    st.markdown('</div>', unsafe_allow_html=True)

    left, right = st.columns([1.1, 1])

    with left:
        video = media_path(memory.get("video"))
        image = media_path(memory.get("image"))
        if video:
            st.video(video)
        elif image:
            st.image(image, use_container_width=True)
        else:
            st.markdown('<div class="memory-card">', unsafe_allow_html=True)
            st.markdown("### 🖼️ 사진/영상 자리")
            st.write("사진이나 영상을 등록하면 이곳에 표시됩니다.")
            st.markdown('</div>', unsafe_allow_html=True)

    with right:
        audio = media_path(memory.get("audio"))
        if audio:
            st.audio(audio)
        else:
            st.info("등록된 음성 파일이 없어서 자막과 기록만 표시됩니다.")

        st.markdown("#### 큰 글씨 자막")
        st.markdown(f'<div class="big-caption">{memory.get("caption")}</div>', unsafe_allow_html=True)

    st.markdown('<div class="memory-card">', unsafe_allow_html=True)
    st.markdown("#### 기억 요약")
    st.write(memory.get("summary"))
    st.markdown("#### 원본 기록")
    st.write(memory.get("story"))
    st.markdown("#### 가족에게 남기는 메시지")
    st.write(memory.get("message"))
    st.markdown("#### 다음에 이어서 물어볼 질문")
    st.info(memory.get("question"))
    st.caption(f"저장 시간: {memory.get('created_at')}")
    st.markdown('</div>', unsafe_allow_html=True)

    receipt = f"""RE:Bloom 기억 영수증

기억 번호: {memory.get('code')}
추억 이름: {memory.get('title')}
저장 시간: {memory.get('created_at')}

다시 이 기억을 보고 싶다면
기억 전화부스에서 {memory.get('code')}번을 입력하세요.
"""
    st.download_button(
        "🧾 기억 영수증 저장하기",
        receipt,
        file_name=f"rebloom_receipt_{memory.get('code')}.txt",
        mime="text/plain",
        use_container_width=True
    )

# -------------------------
# 사이드바
# -------------------------
with st.sidebar:
    st.header("📒 기억 전화번호부")
    memories = load_memories()
    if not memories:
        st.write("아직 저장된 기억이 없습니다.")
    else:
        for memory in memories[:12]:
            st.write(f"{memory.get('code')}  {memory.get('title')}")
    st.divider()
    st.write("기억을 저장하면 번호와 추억 이름이 자동으로 등록됩니다.")

# -------------------------
# 탭 구성
# -------------------------
tab_call, tab_book, tab_record, tab_explain = st.tabs([
    "📞 기억 전화하기",
    "📒 기억 전화번호부",
    "🎙️ 기억 남기기",
    "🧭 프로젝트 설명"
])

with tab_call:
    st.markdown('<div class="phone-box">', unsafe_allow_html=True)
    st.subheader("번호를 입력하세요")
    st.write("저장된 기억 번호를 입력하면 사진/영상, 음성, 자막과 함께 기억이 재생됩니다.")

    input_code = st.text_input("기억 번호", placeholder="예: 4281", max_chars=4)

    c1, c2 = st.columns(2)
    with c1:
        connect = st.button("☎️ 연결하기", use_container_width=True)
    with c2:
        random_connect = st.button("🎲 아무 기억이나 연결하기", use_container_width=True)

    st.markdown('</div>', unsafe_allow_html=True)

    if connect:
        memory = find_memory_by_code(input_code.strip())
        if memory:
            render_memory_player(memory)
        else:
            st.error("해당 번호의 기억을 찾을 수 없습니다. 기억 전화번호부에서 번호를 확인해주세요.")

    if random_connect:
        memories = load_memories()
        if memories:
            render_memory_player(random.choice(memories))
        else:
            st.info("아직 저장된 기억이 없습니다. 먼저 기억을 남겨주세요.")

with tab_book:
    st.subheader("📒 기억 전화번호부")
    st.write("전화번호부에는 번호와 추억 이름만 표시됩니다.")

    memories = load_memories()
    if not memories:
        st.info("아직 저장된 기억이 없습니다.")
    else:
        keyword = st.text_input("추억 이름 검색", placeholder="예: 아버지, 여름, 고향")
        filtered = memories
        if keyword.strip():
            filtered = [m for m in memories if keyword.strip() in m.get("title", "")]

        for memory in filtered:
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f'<div class="phonebook-row">{memory.get("code")} &nbsp;&nbsp; {memory.get("title")}</div>', unsafe_allow_html=True)
            with col2:
                if st.button("연결", key=f"connect_{memory.get('code')}", use_container_width=True):
                    st.session_state["selected_code"] = memory.get("code")

        if "selected_code" in st.session_state:
            selected = find_memory_by_code(st.session_state["selected_code"])
            if selected:
                render_memory_player(selected)

with tab_record:
    st.markdown('<div class="phone-box">', unsafe_allow_html=True)
    st.subheader("기억을 남겨주세요")
    st.write("말하거나 적은 기억은 자동으로 번호가 붙어 전화번호부에 저장됩니다.")

    custom_title = st.text_input(
        "추억 이름",
        placeholder="예: 엄마가 해주던 된장찌개, 첫 월급 받던 날, 아버지와 걷던 밤"
    )
    st.caption("비워두면 입력한 기억 내용을 바탕으로 추억 이름을 자동 생성합니다.")

    visibility = st.selectbox("보관 방식", ["본인만 보관", "가족에게 공유", "사후 공개", "전시용 익명 공개"])
    consent = st.checkbox("이 기억을 저장하고 정리하는 것에 동의합니다.")

    input_type = st.radio("입력 방식", ["텍스트 입력", "음성 파일 업로드"], horizontal=True)
    story = ""

    uploaded_audio_for_record = None
    if input_type == "텍스트 입력":
        story = st.text_area(
            "기억을 자유롭게 적어주세요.",
            height=230,
            placeholder="예: 어릴 때 우리 집 마당에는 감나무가 있었고, 어머니가 가을마다 감을 따서 말려주셨습니다..."
        )
    else:
        st.info("프로토타입은 1~3분 음성 파일을 권장합니다. 실제 서비스에서는 긴 음성을 나누어 저장하도록 확장할 수 있습니다.")
        uploaded_audio_for_record = st.file_uploader("음성 파일 업로드 mp3/wav/m4a", type=["mp3", "wav", "m4a"], key="record_audio")
        if uploaded_audio_for_record:
            st.audio(uploaded_audio_for_record)
            if st.button("🎤 음성을 글로 변환하기", use_container_width=True):
                with st.spinner("음성을 텍스트로 변환 중입니다..."):
                    transcript, error = transcribe_audio(uploaded_audio_for_record)
                if error:
                    st.error(error)
                else:
                    st.session_state["transcript"] = transcript
                    st.success("음성 변환 완료")
        story = st.text_area(
            "변환된 텍스트를 확인하고 수정할 수 있습니다.",
            value=st.session_state.get("transcript", ""),
            height=230
        )

    st.markdown("#### 사진/영상 추가")
    st.write("선택 사항입니다. 등록하면 번호 연결 시 함께 표시됩니다.")
    image_upload = st.file_uploader("사진 업로드", type=["jpg", "jpeg", "png"], key="image_upload")
    video_upload = st.file_uploader("영상 업로드", type=["mp4", "mov"], key="video_upload")

    st.markdown('</div>', unsafe_allow_html=True)

    if st.button("📞 통화 종료 및 기억 저장하기", use_container_width=True):
        if not consent:
            st.error("저장 동의가 필요합니다.")
        elif not story.strip():
            st.error("기억 내용을 입력하거나 음성 변환을 완료해주세요.")
        else:
            with st.spinner("기억을 정리하고 전화번호부에 등록하고 있습니다..."):
                classified = ai_classify_memory(story)
                code = make_memory_code()

                title = custom_title.strip() if custom_title.strip() else classified.get("title", "오늘의 기억")

                audio_filename = ""
                if uploaded_audio_for_record is not None:
                    audio_filename = save_uploaded_file(uploaded_audio_for_record, code, "audio")

                image_filename = save_uploaded_file(image_upload, code, "image")
                video_filename = save_uploaded_file(video_upload, code, "video")

                memory = {
                    "code": code,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "visibility": visibility,
                    "input_type": input_type,
                    "story": story,
                    "title": title,
                    "summary": classified.get("summary", "요약 없음"),
                    "caption": classified.get("caption", story[:160]),
                    "question": classified.get("question", ""),
                    "message": classified.get("message", ""),
                    "audio": audio_filename,
                    "image": image_filename,
                    "video": video_filename
                }
                save_memory(memory)

            st.success(f"기억이 저장되었습니다. 기억 번호는 {code} 입니다.")
            render_memory_player(memory)

with tab_explain:
    st.subheader("🧭 프로젝트 설명")
    st.markdown("""
### 서비스 방향
RE:Bloom은 한 사람의 추억을 계속 기록하는 개인 기억 전화부스입니다.  
사용자가 텍스트 또는 음성으로 기억을 남기면, 시스템이 추억 이름과 기억 번호를 부여하고 전화번호부에 저장합니다.

### 사용 흐름
1. 사용자가 추억 이름을 적습니다. 비워두면 자동으로 생성됩니다.  
2. 사용자가 기억을 말하거나 적습니다.  
3. 기록이 저장되면 기억 번호가 생성됩니다.  
4. 기억 전화번호부에는 번호와 추억 이름만 표시됩니다.  
5. 이후 번호를 입력하면 해당 기억이 다시 재생됩니다.  
6. 사진, 영상, 음성 파일이 있으면 함께 표시됩니다.

### 데이터 수집 방법
실제 운영에서는 다음 방식으로 기록을 모을 수 있습니다.

1. **부스 내 직접 녹음**  
사용자가 기기 앞에서 직접 자신의 기억을 말합니다.

2. **인터뷰 기반 수집**  
복지관, 요양원, 마을회관 등에서 인터뷰어가 질문을 던지고 기록합니다.

3. **가족 자료 업로드**  
가족이 사진, 음성, 영상, 편지 등을 제공하면 기억 기록에 연결합니다.

4. **이동형 기록 키트**  
부스 방문이 어려운 어르신을 위해 직접 방문해 기록합니다.

5. **기억 카드 작성**  
말로 표현하기 어려운 사용자를 위해 종이 카드에 짧게 적고 이를 디지털화합니다.

### 기록 처리 흐름
- 음성 파일을 텍스트로 변환
- 원본 기록 저장
- 추억 이름 저장 또는 자동 생성
- 기억 번호 자동 부여
- 전화번호부에 저장
- 번호 입력 시 기억 재생
""")

st.divider()
st.caption("RE:Bloom은 한 사람의 삶을 기록하고, 다시 꺼내 들을 수 있게 만드는 기억 전화부스입니다.")
