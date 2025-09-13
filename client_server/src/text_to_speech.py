#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
텍스트를 음성으로 변환하는 스크립트
서버에서 받은 텍스트 메시지를 음성으로 출력
메모리에서 직접 재생 (파일 저장 없음)
C 클라이언트에서 호출되어 사용됨
"""

import sys
from gtts import gTTS
import pygame
import io

def main():
    # 명령행 인수가 없으면 종료
    if len(sys.argv) < 2:
        sys.exit(1)
    
    # 명령행 인수들을 하나의 문자열로 합치기
    text = " ".join(sys.argv[1:])
    
    # 텍스트가 비어있으면 종료
    if not text or len(text.strip()) < 2:
        sys.exit(1)
    
    try:
        # gTTS 객체 생성 (언어는 한국어로 설정)
        tts = gTTS(text=text.strip(), lang='ko')
        
        # 음성을 메모리에서 직접 재생하기 위해 파일로 저장하지 않고 BytesIO를 사용
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        
        # pygame 초기화
        pygame.mixer.init()
        
        # 파일 포인터를 처음으로 돌려놓습니다
        fp.seek(0)
        
        # pygame에서 음성 재생
        pygame.mixer.music.load(fp, "mp3")
        pygame.mixer.music.play()
        
        # 음성이 끝날 때까지 기다림
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        
    except Exception as e:
        # 오류 발생 시 조용히 종료 (C 코드에서 오류 처리)
        sys.exit(1)

if __name__ == "__main__":
    main()