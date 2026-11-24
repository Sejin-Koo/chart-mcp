# chart-mcp

보고서용 차트 75종을 그리는 MCP 서버입니다. 계정(Claude 채팅)과 업무 에이전트가 같은 코드로 그려 모양이 같습니다.

- 엔진: matplotlib(맑은 고딕, 계정 보고서 색 규칙 — 남색·청록·주황 + 보라·황토·자주)
- 범위: 차트 BOOK·유통·신약개발 카탈로그 106종 중 75종. 막대·꺾은선·원 같은 기본 그래프 28종과 도식 3종은 보고서 변환기(sys-file-builder의 ```chart·```diagram)가 맡습니다.
- 결과: PNG(보고서 본문 폭 16cm·220dpi) + 엑셀 원본(엑셀 차트 46종 · 표 색 단계 8종 · 그림 21종)
- 계산: 카플란-마이어·log-rank·4PL(EC50)·PK(Cmax·AUC·t½)·추세선·관리 한계·상관계수 등은 서버가 계산해 `computed`·`notes`로 돌려줍니다.

## 구조

| 경로 | 내용 |
|---|---|
| `api/mcp.py` | MCP 서버(Vercel 파이썬 함수, ASGI, JSON-RPC 직접 구현) — 게이트 `?k=`, 프로토콜 협상·헤더 검사 |
| `chartkit/api.py` | `draw(type, data, …)` · `to_xlsx(result)` · `list_types()` |
| `chartkit/render/` | 종류별 그리기(category·xy·distribution·matrix·hierarchy·flow·timeline·geo·finance), `legacy/`는 임상·오믹스·특수 차트(원본 엔진) |
| `chartkit/excel.py` | 엑셀 원본 |
| `chartkit/catalog.json` | 75종 목록과 예시 입력 |
| `chartkit/maps/korea_sido.geo.json` | 시·도 경계(17개). 전남광주통합특별시 이름은 광주·전남을 같은 값으로 칠함 |

## 도구

- `list_chart_types(code?, tag?)` — 목록, code를 주면 예시 입력
- `draw_chart(type, data, title?, subtitle?, unit?, options?, output?, include_xlsx?)` — output: `image`(기본) · `base64` · `xlsx`
- `chart_server_status()` — 글꼴·게이트 상태(비밀값 없음)

## 글꼴

맑은 고딕은 저장소에 넣지 않습니다. 서버는 환경변수 `FONT_URL_REGULAR`·`FONT_URL_BOLD`(비공개 주소, `|`로 조각 주소를 이으면 순서대로 받아 붙임)에서 받아 `/tmp`에 둡니다. 없으면 대체 글꼴로 그리고 응답 `notes`에 알립니다.

## 환경변수

| 이름 | 뜻 |
|---|---|
| `MCP_GATE_KEYS` | 허용 게이트키(쉼표 구분) |
| `MCP_GATE_MODE` | `enforce`(차단) · `observe` |
| `FONT_URL_REGULAR`, `FONT_URL_BOLD` | 맑은 고딕 받는 주소 |

## 명령줄(계정 작업 공간)

```bash
pip install -r requirements.txt
python -m chartkit list
python -m chartkit example R-05 > spec.json
python -m chartkit draw spec.json out.png out.xlsx
python tests/smoke.py   # 75종 전부 그리기 + 엑셀
```
