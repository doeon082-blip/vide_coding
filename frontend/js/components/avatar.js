// 화면 조각: '값을 받아 DOM 요소를 돌려주는 함수'. 글자는 el()의 text/자식(= textContent)으로만 넣고, 링크는 view-model이 허용 목록을 통과시킨 href만 받는다.

import { el } from "../lib/dom.js";

/** 답 말풍선 옆의 로고(내부 그림 파일). */
export const avatar = () => el("img", { class: "avatar", src: "img/mark.svg", alt: "", width: "32", height: "32" });
