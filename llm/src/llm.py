import os
import time
import re
import base64
import threading
import queue
from collections import deque

import cv2
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import ollama

# ---------------------------
# 설정값
# ---------------------------
MODEL_NAME = "moondream:latest"   # llava 계열로 바꿔도 동일하게 동작
TARGET_WIDTH = 640                # 분석 프레임 리사이즈 폭
JPEG_QUALITY = 82
MOTION_THRESH = 18_000            # 모션(변화량) 임계값(실험으로 보정)
COOLDOWN_MIN = 2.0                # 최소 분석 간격(초)
ADAPTIVE_FACTOR = 1.2             # 인퍼런스 시간 기반 적응 계수
MAJORITY_WINDOW = 5               # 최근 N회 결과 다수결
OLLAMA_TIMEOUT = 25.0             # 초
PRINT_EVERY = 1.0                 # 로깅 간격(초)

HAZARD_PATTERNS = [
    # 영어
    r"\b(flame|blaze|fire|smoke|burn(ing)?\s*object|ignition)\b",
    r"\b(gun|knife|weapon|explosion|threat)\b",
    r"\b(fall(ing)?|ladder|no\s*harness|no\s*safety\s*line|at\s*height|construction|danger|hazard)\b",
    r"\b(crash|collision|overturn|rollover|airbag|wreckage|damaged\s*vehicle)\b",
]

NLI_MODEL_NAME = "MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli"

# ---------------------------
# 유틸 함수
# ---------------------------
def classify_text_regex(text: str) -> str:
    t = text.lower()
    for p in HAZARD_PATTERNS:
        if re.search(p, t):
            return "위험"
    return "안전"

def load_nli():
    tokenizer = AutoTokenizer.from_pretrained(NLI_MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(NLI_MODEL_NAME)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        model = model.half().to(device)
    id2label = model.config.id2label
    label_map_upper = {i: lbl.upper() for i, lbl in id2label.items()}
    entail_idx = [i for i, lbl in label_map_upper.items() if "ENTAIL" in lbl][0]
    contra_idx  = [i for i, lbl in label_map_upper.items() if "CONTRADICT" in lbl][0]
    neutral_idx = [i for i, lbl in label_map_upper.items() if "NEUTRAL" in lbl][0]
    return tokenizer, model, device, entail_idx, contra_idx, neutral_idx

tokenizer, nli_model, device, ENTAIL_IDX, CONTRA_IDX, NEUTRAL_IDX = load_nli()

def nli_danger(text: str, threshold: float = 0.6) -> str:
    # 영어 가설이 성능 안정적인 편
    premise = text
    hypothesis = "it is dangerous."
    inputs = tokenizer(premise, hypothesis, return_tensors="pt", truncation=True)
    if device == "cuda":
        inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        logits = nli_model(**inputs).logits.squeeze(0)
        probs = torch.softmax(logits, dim=-1).float().cpu().numpy().tolist()
    return "위험" if probs[ENTAIL_IDX] >= threshold else "안전"

def to_base64_jpeg(img_bgr: np.ndarray, width: int, quality: int) -> str:
    h, w = img_bgr.shape[:2]
    if w != width:
        scale = width / w
        img_bgr = cv2.resize(img_bgr, (width, int(h*scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("JPEG 인코딩 실패")
    return base64.b64encode(buf).decode("ascii")

def ollama_describe(b64jpg: str, model: str, timeout: float = OLLAMA_TIMEOUT) -> str:
    # ollama Python client는 images에 base64 문자열을 허용
    start = time.time()
    resp = ollama.chat(
        model=model,
        messages=[{
            "role": "user",
            "content": "Describe this image briefly and factually.",
            "images": [b64jpg]
        }],
        options={"timeout": timeout}
    )
    took = time.time() - start
    return resp["message"]["content"], took

def motion_score(prev_gray: np.ndarray, gray: np.ndarray) -> float:
    # 간단한 프레임 차 기반 모션 측정
    diff = cv2.absdiff(prev_gray, gray)
    diff = cv2.GaussianBlur(diff, (5,5), 0)
    _, th = cv2.threshold(diff, 18, 255, cv2.THRESH_BINARY)
    return float(cv2.countNonZero(th))

# ---------------------------
# 파이프라인(Producer/Consumer)
# ---------------------------
frame_q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=3)
result_q: "queue.Queue[tuple[str,str,float,float]]" = queue.Queue(maxsize=10)
stop_flag = False

def capture_loop():
    global stop_flag
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("웹캠을 열 수 없습니다. 연결 상태를 확인해주세요.")
    # 해상도(가능하면 드라이버에 힌트)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    last_log = 0.0
    prev_gray = None
    last_push_t = 0.0
    last_infer_duration = 3.0
    adaptive_cooldown = max(COOLDOWN_MIN, last_infer_duration * ADAPTIVE_FACTOR)

    while not stop_flag:
        ret, frame = cap.read()
        if not ret:
            print("프레임 읽기 실패")
            break

        # 표시용
        disp = frame.copy()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # 모션 측정
        mscore = motion_score(prev_gray, gray) if prev_gray is not None else 0.0
        prev_gray = gray

        now = time.time()
        # 적응형 쿨다운 갱신(최근 인퍼런스 시간 기반)
        adaptive_cooldown = max(COOLDOWN_MIN, last_infer_duration * ADAPTIVE_FACTOR)

        # 조건 충족 시 프레임 큐에 제출
        should_push = (mscore >= MOTION_THRESH) and (now - last_push_t >= adaptive_cooldown)
        status_text = f"motion={int(mscore)} cool={adaptive_cooldown:.1f}s"
        color = (0, 255, 0) if not should_push else (0, 200, 255)

        if should_push:
            try:
                if not frame_q.full():
                    frame_q.put_nowait(frame)
                    last_push_t = now
            except queue.Full:
                pass

        # 화면 표시
        cv2.putText(disp, status_text, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        cv2.imshow("Ollama Webcam Description (Optimized)", disp)

        # 주기적 로그
        if now - last_log >= PRINT_EVERY:
            last_log = now

        if (cv2.waitKey(1) & 0xFF) == ord('q'):
            stop_flag = True
            break

    cap.release()
    cv2.destroyAllWindows()

def analyze_loop():
    global stop_flag
    history = deque(maxlen=MAJORITY_WINDOW)
    last_print = 0.0
    while not stop_flag:
        try:
            frame = frame_q.get(timeout=0.1)
        except queue.Empty:
            continue

        try:
            b64 = to_base64_jpeg(frame, TARGET_WIDTH, JPEG_QUALITY)
            print(f"[{time.strftime('%H:%M:%S')}] 이미지를 분석하는 중...")
            desc, took = ollama_describe(b64, MODEL_NAME)
            regex_label = classify_text_regex(desc)
            nli_label = nli_danger(desc, threshold=0.6)
            final = "위험" if ("위험" in (regex_label, nli_label)) else "안전"
            history.append(final)

            # 다수결 스무딩
            votes = sum(1 for x in history if x == "위험")
            majority = "위험" if votes > len(history) / 2 else "안전"

            result_q.put_nowait((majority, desc, took, time.time()))

            print(f"모델 응답: {desc}")
            print(f"-> 분류(개별: {final}, 다수결: {majority}) | took={took:.2f}s")

        except Exception as e:
            print(f"Ollama/NLI 오류: {e}")

# ---------------------------
# 실행
# ---------------------------
if __name__ == "__main__":
    print(f"웹캠 분석 시작. 모델: {MODEL_NAME}")
    print("'q' 키로 종료합니다.")

    t_cap = threading.Thread(target=capture_loop, daemon=True)
    t_ana = threading.Thread(target=analyze_loop, daemon=True)

    t_cap.start()
    t_ana.start()

    try:
        # 메인 스레드는 최근 결과를 적당히 출력
        while not stop_flag:
            try:
                majority, desc, took, ts = result_q.get(timeout=0.2)
                # 최근 결과 요약 출력(필요시 파일/DB 로깅 가능)
                print(f"[{time.strftime('%H:%M:%S', time.localtime(ts))}] 최종: {majority} | 인퍼런스 {took:.2f}s")
            except queue.Empty:
                pass
            time.sleep(0.05)
    finally:
        stop_flag = True
        t_cap.join(timeout=1.0)
        t_ana.join(timeout=1.0)
        print("프로그램이 종료되었습니다.")
