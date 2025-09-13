#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
음성인식 스크립트 - C 클라이언트에서 호출
음성을 텍스트로 변환하여 표준출력으로 반환
"""

import speech_recognition as sr
from gtts import gTTS
import os
import sys

def main():
    """
    음성인식을 수행하고 텍스트를 표준출력으로 반환
    """
    try:
        # Recognizer 객체 생성
        recognizer = sr.Recognizer()
        
        # "말을 해주세요" 음성을 먼저 출력
        welcome_message = "3초 뒤에 말을 해주세요"
        tts_welcome = gTTS(text=welcome_message, lang='ko', slow=False)
        tts_welcome.save("welcome.mp3")
        
        # 운영체제에 따른 음성 재생
        if os.name == 'nt':  # Windows
            os.system("start welcome.mp3")
        else:  # Linux/Unix
            os.system("mpg321 welcome.mp3")
        
        # 마이크로부터 음성 입력 받기
        with sr.Microphone() as source:
            # 배경 소음 조정
            recognizer.adjust_for_ambient_noise(source, duration=1)
            
            # 음성 입력 받기
            audio = recognizer.listen(source)
            
            try:
                # 음성을 텍스트로 변환
                text = recognizer.recognize_google(audio, language='ko-KR')
                
                # 인식된 텍스트를 표준출력으로 반환 (C 클라이언트가 읽을 수 있도록)
                print(text)
                
            except sr.UnknownValueError:
                print("음성을 인식할 수 없습니다.")
            except sr.RequestError as e:
                print(f"구글 음성 인식 서비스에 문제가 발생했습니다: {e}")
                
    except Exception as e:
        print(f"음성인식 중 오류 발생: {e}")

if __name__ == "__main__":
    main()
