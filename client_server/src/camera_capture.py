#!/usr/bin/env python3
"""
인텔 리얼카메라 이미지 캡처 스크립트
C언어 클라이언트에서 호출되어 RGB와 Depth 이미지를 캡처하고 파일로 저장
"""

import pyrealsense2 as rs
import numpy as np
import cv2
import os
import sys
from datetime import datetime

def capture_images():
    """RGB와 Depth 이미지를 캡처하여 파일로 저장"""
    
    # 파이프라인 설정
    pipeline = rs.pipeline()
    config = rs.config()

    # Depth 스트림과 컬러 스트림 설정
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

    try:
        # 파이프라인 시작
        pipeline.start(config)
        
        # 카메라 내부 파라미터 가져오기
        depth_intrin = pipeline.get_active_profile().get_stream(rs.stream.depth).as_video_stream_profile().intrinsics

        # 깊이 영상의 최대값과 최소값 설정
        min_distance = 0.1  # 최소 거리 (10cm)
        max_distance = 3.0  # 최대 거리 (3m)

        print("카메라 초기화 중...")
        
        # 몇 프레임을 건너뛰어 카메라가 안정화되도록 함
        for _ in range(10):
            frames = pipeline.wait_for_frames()
        
        print("이미지 캡처 중...")
        
        # 프레임 받아오기
        frames = pipeline.wait_for_frames()
        depth_frame = frames.get_depth_frame()
        color_frame = frames.get_color_frame()

        # 카메라에서 프레임을 받지 못한 경우 에러 처리
        if not depth_frame or not color_frame:
            print("Error: Failed to capture frames")
            return False

        # 깊이 영상 데이터 가져오기
        depth_image = np.asanyarray(depth_frame.get_data())

        # 컬러 영상 데이터 가져오기
        color_image = np.asanyarray(color_frame.get_data())

        # 깊이 값을 색상 맵으로 변환
        depth_colormap = cv2.convertScaleAbs(depth_image, alpha=0.03)  # 깊이 데이터를 8비트로 변환
        depth_colormap = cv2.applyColorMap(depth_colormap, cv2.COLORMAP_JET)  # Jet 컬러맵 적용

        # 색상이 잘 적용되도록 깊이 값의 범위를 조정
        norm_depth = cv2.normalize(depth_image, None, min_distance, max_distance, cv2.NORM_MINMAX)
        norm_depth_colormap = cv2.applyColorMap((norm_depth * 255).astype(np.uint8), cv2.COLORMAP_JET)

        # 3개의 좌표에서 거리 측정 (미터 단위로 계산)
        x_center, y_center = 320, 240  # 화면 중심 (640x480 해상도)
        x_left, y_left = 160, 240      # 좌측 (가로 160 픽셀)
        x_right, y_right = 480, 240     # 우측 (가로 480 픽셀)

        # 깊이 값을 사용해 3D 좌표 계산 (미터 단위)
        def get_3d_coordinates(x, y, depth_frame):
            # 깊이 값 가져오기
            depth = depth_frame.get_distance(x, y)
            
            # 카메라 내부 파라미터 사용
            fx, fy = depth_intrin.fx, depth_intrin.fy
            ppx, ppy = depth_intrin.ppx, depth_intrin.ppy

            # 3D 좌표 계산 (미터 단위)
            x_3d = (x - ppx) * depth / fx
            y_3d = (y - ppy) * depth / fy
            z_3d = depth

            return x_3d, y_3d, z_3d

        # 각 좌표에서의 3D 좌표 계산
        center_3d = get_3d_coordinates(x_center, y_center, depth_frame)
        left_3d = get_3d_coordinates(x_left, y_left, depth_frame)
        right_3d = get_3d_coordinates(x_right, y_right, depth_frame)

        # 각 거리값을 화면에 표시 (미터 단위로 출력)
        cv2.putText(color_image, f"Center: {center_3d[2]:.2f} m", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(color_image, f"Left: {left_3d[2]:.2f} m", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(color_image, f"Right: {right_3d[2]:.2f} m", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        # 거리 정보를 Depth 이미지에도 표시
        cv2.putText(norm_depth_colormap, f"Center: {center_3d[2]:.2f} m", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(norm_depth_colormap, f"Left: {left_3d[2]:.2f} m", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(norm_depth_colormap, f"Right: {right_3d[2]:.2f} m", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        # 현재 시간을 파일명에 포함
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # RGB 이미지 저장
        rgb_filename = "captured_rgb.jpg"
        cv2.imwrite(rgb_filename, color_image)
        print(f"RGB 이미지 저장 완료: {rgb_filename}")

        # Depth 이미지 저장
        depth_filename = "captured_depth.jpg"
        cv2.imwrite(depth_filename, norm_depth_colormap)
        print(f"Depth 이미지 저장 완료: {depth_filename}")

        # 거리 정보를 텍스트 파일로도 저장
        info_filename = "captured_info.txt"
        with open(info_filename, 'w') as f:
            f.write(f"Image Capture Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Center Distance: {center_3d[2]:.3f} m\n")
            f.write(f"Left Distance: {left_3d[2]:.3f} m\n")
            f.write(f"Right Distance: {right_3d[2]:.3f} m\n")
            f.write(f"Center 3D Coordinates: ({center_3d[0]:.3f}, {center_3d[1]:.3f}, {center_3d[2]:.3f})\n")
            f.write(f"Left 3D Coordinates: ({left_3d[0]:.3f}, {left_3d[1]:.3f}, {left_3d[2]:.3f})\n")
            f.write(f"Right 3D Coordinates: ({right_3d[0]:.3f}, {right_3d[1]:.3f}, {right_3d[2]:.3f})\n")
        print(f"거리 정보 저장 완료: {info_filename}")

        return True

    except Exception as e:
        print(f"Error during image capture: {e}")
        return False

    finally:
        # 파이프라인 종료
        try:
            pipeline.stop()
        except:
            pass

def main():
    """메인 함수"""
    print("=== Intel RealSense Camera Image Capture ===")
    
    # 이미지 캡처 실행
    success = capture_images()
    
    if success:
        print("이미지 캡처가 성공적으로 완료되었습니다.")
        sys.exit(0)  # 성공
    else:
        print("이미지 캡처에 실패했습니다.")
        sys.exit(1)  # 실패

if __name__ == "__main__":
    main()
