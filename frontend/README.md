# 채산 화면 (frontend)

한국체육산업개발 공개 자료로 답하는 **비공식** 안내 서비스 "채산"의 화면입니다.
**빌드가 없습니다.** HTML + CSS + 순수 자바스크립트(ES 모듈)이고 npm 패키지에 의존하지 않습니다. 파일을 그대로 열어 구조를 볼 수 있습니다.

## 구조
```
index.html              뼈대(채팅형 화면). 인라인 코드 없음, CSP 메타 포함
css/                    base(색·글자·갈래 색) / layout(배치·입력창) / card(말풍선·답변 카드)
                        evidence(그래프·표·목록) / chat(입력 중 표시·이어 묻기)
js/main.js              시작점: 상태를 만들고 아래 조각들을 연결
js/state.js             상태 하나와 상태를 바꾸는 순수 함수(대화는 메모리에만, 저장하지 않음)
js/api.js               서버 호출(POST api/chaesan/ask), 30초 제한, 오류 분류
js/composer.js          아래에 붙은 입력창: Enter 전송, 한글 조합 중 Enter 무시, 글자 수
js/render.js            render(state): 대화 영역을 통째로 다시 그림
js/scroll.js            새 메시지가 생겼을 때의 스크롤(긴 답은 처음부터)
js/examples.js          예시 질문과 미리 계산한 답(data/examples.json) 읽기
js/clipboard.js         답 복사
js/components.js        components/ 입구(render.js가 여기서만 가져다 씀)
js/components/          조각마다 한 파일: answer-card, answer-block, badges, bar-chart, evidence, evidence-table,
                        documents, sources, suggestions, user-bubble, typing-bubble, avatar, copy-button, link
js/view-model.js        view-model/ 입구
js/view-model/          서버 응답 → 화면 값(DOM 없음): answer(숫자 미확인이면 답을 숨김), table(표·그래프 값),
                        documents, sources, failure, follow-ups, constants, guards
js/lib/                 dom(textContent만 쓰는 요소 생성) / safe-url(https+허용 도메인) / format / lane / mode
img/                    직접 그린 공원 일러스트(밝은·어두운 판), 갈래 아이콘, 로고
data/examples.json      실제 엔진이 낸 미리 계산한 답 10개(backend/eval/build_examples.py가 생성)
tests/                  node --test 시험(링크 검사·값 정리·서버 호출·상태·예비 모드)
```

## 실행
서버와 같은 주소로 열립니다(CORS 설정 불필요). 저장소 루트에서:
```bash
cd backend
uv run uvicorn app.chaesan.local.app:app --port 8100 --no-proxy-headers
# 브라우저: http://localhost:8100/
```
서버 없이 보려면 `?offline=1`을 붙입니다(미리 계산한 예시 답만 동작). GitHub Pages 같은 `*.github.io` 주소는 자동으로 이 모드입니다.

## 시험
```bash
cd frontend
npm test        # node --test tests/ (의존성 설치 없음)
```

## 지키는 규칙
- 서버가 준 글자는 `textContent`로만 넣습니다(`innerHTML` 등 금지). 링크는 `https` + `data.go.kr`·`ksponco.or.kr`·`alio.go.kr`만.
- 외부 CDN·글꼴·추적 스크립트 없음. 질문 원문은 브라우저 저장소·서버에 저장하지 않습니다.
- 스타일은 CSS 클래스로만 바꿉니다(CSP가 인라인 스타일을 막음).
- 모든 화면에 "비공식 서비스"를 표시합니다. 기관 로고·색을 흉내 내지 않습니다.
