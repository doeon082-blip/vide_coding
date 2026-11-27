"""경로와 판정 기준값. 결과를 보기 전에 고정한 값이라 바꾸려면 먼저 사용자에게 말한다."""

from __future__ import annotations

from pathlib import Path

# app.database(ChromaDB)를 import하지 않으려고 파일 위치에서 직접 계산한다.
BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "data"  # gitignore 대상(원본 재배포 금지)
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
REPORT_DIR = DATA_DIR / "report"

# --- 구역 -------------------------------------------------------------
# 거리는 미터 좌표계(EPSG:5179)에서 공원 경계까지의 최단거리로 잰다.
PLANAR_CRS = "EPSG:5179"  # 한국 전역 미터 좌표계(격자 파일이 쓰는 좌표계)
GEO_CRS = "EPSG:4326"  # 위도·경도(geojson.io가 내보내는 좌표계)
RING1_MAX_M = 500.0  # park 밖 0~500m
RING2_MAX_M = 1500.0  # 500m~1.5km
ZONES = ("park", "ring1", "ring2")

# 대한민국 범위(경위도). GeoJSON은 [경도, 위도] 순서라 뒤집어 넣는 실수를 잡는 데 쓴다.
KOREA_LON_RANGE = (124.0, 132.0)
KOREA_LAT_RANGE = (33.0, 39.0)

# --- 효과 판정 (D단계) ------------------------------------------------
BASELINE_WINDOW_DAYS = 28  # 날짜 앞뒤 28일 안에서 같은 요일만 본다
BASELINE_MIN_DAYS = 4  # 이보다 적으면 "판정 불가"
SCORE_HOURS_BEFORE = 3  # 점수 창: 시작 시각 3시간 전 ...
SCORE_HOURS_AFTER = 3  # ... 3시간 후 (시작 시각 포함 7칸)
PLACEBO_PERCENTILE = 95.0  # 위약 검정 문턱값
PASS_RATIO = 0.5  # 통과 기준: 판정 가능한 행사일 중 절반 이상
PASS_ZONES = ("park", "ring1")  # 이 중 하나라도 문턱값을 넘으면 그 행사는 통과
JUDGE_START = "2025-09-01"  # 판정 대상 기간(양 끝 포함). 8월·12월은 기준값 재료로만 쓴다
JUDGE_END = "2025-11-30"
SUPPRESSED_FILL_VALUES = (0.0, 3.0)  # '*'(비식별)를 0과 3으로 각각 계산해 판정 비교
