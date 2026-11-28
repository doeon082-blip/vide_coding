// 화면이 서버 없이(예비 모드) 동작해야 하는지 판단한다. 순수 함수라서 시험하기 쉽다.
// - 주소에 ?offline=1 이 있으면 예비 모드.
// - GitHub Pages(*.github.io) 같은 정적 호스팅에는 채산 서버가 없으므로 자동으로 예비 모드(미리 계산한 예시 답만 보여 준다).

export function detectOffline(search, hostname) {
  if (new URLSearchParams(search).get("offline") === "1") return true;
  return typeof hostname === "string" && hostname.toLowerCase().endsWith(".github.io");
}
