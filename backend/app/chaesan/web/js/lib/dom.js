// 요소 만들기 도우미. 서버에서 온 글자는 반드시 이 도우미(textContent)로만 화면에 넣는다.
// 왜: innerHTML 등을 쓰면 데이터·AI 답 속 '<script>' 같은 문장이 HTML로 해석돼 실행될 수 있다(XSS).
// 그래서 이벤트 속성(onclick...), style, srcdoc은 아예 만들 수 없게 막고, 주소 속성(href·src)은 safeUrl을 통과해야 한다.

import { safeUrl } from "./safe-url.js";

const BLOCKED_ATTR = /^(on|style$|srcdoc$|formaction$)/i;
const URL_ATTR = /^(href|src|action|xlink:href)$/i;

/** 속성 이름이 안전한가(글자·숫자·_-: 만, 이벤트·style 제외). 시험하려고 따로 내보낸다. */
export function isSafeAttr(name) {
  return typeof name === "string" && /^[a-zA-Z][\w:-]*$/.test(name) && !BLOCKED_ATTR.test(name);
}

/**
 * el("p", { class: "note", text: "글자" }, 자식...) → <p class="note">글자</p>
 * - text는 textContent로, 자식 문자열은 글자 노드로 들어간다.
 * - null·undefined·false 값/자식은 건너뛴다.
 */
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props ?? {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "text") {
      node.textContent = String(value);
    } else if (key === "class") {
      node.className = String(value);
    } else if (!isSafeAttr(key)) {
      throw new Error(`허용하지 않는 속성: ${key}`);
    } else if (URL_ATTR.test(key)) {
      const safe = safeUrl(String(value));
      if (safe === null) throw new Error("허용하지 않는 주소");
      node.setAttribute(key, safe);
    } else {
      node.setAttribute(key, value === true ? "" : String(value));
    }
  }
  for (const child of children.flat()) {
    if (child === undefined || child === null || child === false) continue;
    node.append(typeof child === "object" ? child : String(child)); // 문자열은 append가 글자 노드로 넣는다(HTML 해석 없음)
  }
  return node;
}
