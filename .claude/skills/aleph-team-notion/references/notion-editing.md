# Notion 편집 요령 (브라우저)

10/22~10/23 팀 Notion 작업에서 실제로 확인한 방법입니다. Notion 화면 구조(클래스 이름 등)는 바뀔 수 있으므로, 결과는 항상 화면이나 다시 읽기로 확인합니다. 페이지 읽기에는 스크린샷보다 텍스트 추출(`get_page_text`, `read_page`, 페이지 JS)이 정확합니다.

## 본문 넣기: 마크다운 붙여넣기

빈 텍스트 블록에 `paste` 이벤트로 마크다운을 넣으면 제목(`##`), 목록, 번호 목록, 인용(`>`), 굵게, 인라인 코드, 링크, **마크다운 표**가 Notion 블록으로 바뀝니다. 한 번에 긴 본문을 넣을 수 있어 글자를 직접 치는 것보다 빠르고 정확합니다.

```js
const blk = document.querySelector('[data-block-id="<빈 블록 ID>"]');
const ed = blk.querySelector('[contenteditable="true"]');
ed.focus();
const dt = new DataTransfer();
dt.setData('text/plain', md);  // md: 넣을 마크다운 문자열
ed.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
```

- 목록 블록 끝에서 붙여넣으면 첫 줄이 목록에 섞일 수 있으니, 새 빈 줄(텍스트 블록)을 만든 뒤 붙여넣습니다.
- 도구의 `type` 동작으로 `## `을 치면 제목 단축키가 동작하지 않고 글자로 남습니다. 제목은 붙여넣기로 넣습니다.
- 붙여넣기 뒤 "추천 작업" 팝업이 뜨면 Esc로 닫습니다.

## 하위 페이지 만들기

1. 넣을 위치의 블록에 마우스를 올리고 왼쪽 `+`를 누르거나, 빈 줄을 실제로 클릭해 커서를 둔 뒤 `/page`를 입력합니다.
2. 메뉴에서 "페이지"가 선택된 것을 확인하고 Enter를 누르면 새 하위 페이지가 열립니다.
3. 제목을 입력하고 Enter를 누르면 본문 첫 줄로 넘어갑니다. 여기에 위 방법으로 붙여넣습니다.

JS로 `focus()`만 한 상태에서는 Enter·`/page` 같은 키 입력이 다른 곳으로 갈 수 있습니다. 키 입력 전에는 실제 클릭으로 커서를 두고, 커서가 들어간 블록을 `getSelection()`으로 확인합니다.

## 블록 선택과 삭제

- 블록 글자를 클릭해 커서를 둔 뒤 Esc를 누르면 그 블록이 파랗게 선택됩니다. Shift+↓로 아래 블록까지 넓힙니다.
- 키를 빠르게 반복하면 Notion이 일부를 놓칩니다(70번 중 20여 번만 반영된 적 있음). 10번씩 나누고 사이에 1초 정도 기다립니다.
- 지우기 전에 선택의 첫 블록과 끝 블록, 바로 바깥 블록이 선택되지 않았는지 화면으로 확인합니다. DOM의 `.notion-selectable-halo`만으로는 판단하기 어렵습니다.
- 페이지 블록을 지우면 그 페이지가 휴지통으로 갑니다. 페이지 링크를 지우려는 것인지 페이지 자체를 지우려는 것인지 구분합니다.

## 페이지를 다른 페이지 안으로 옮기기

블록 왼쪽 손잡이(⋮⋮)를 눌러 메뉴를 열고 **옮기기**(Ctrl+Shift+P)를 고른 뒤, 목록에서 대상 페이지를 클릭합니다. 옮긴 페이지는 대상 페이지 맨 끝에 붙습니다. 검색창이 뜨기 전에 친 글자는 들어가지 않으므로, 창이 뜬 것을 본 뒤 목록에서 고릅니다.

## 같은 페이지 안에서 순서 바꾸기

- 블록을 선택한 채 Ctrl+Shift+↑/↓로 한 칸씩 옮깁니다. 한 번 누를 때마다 1초쯤 기다립니다.
- 글머리표·번호 목록 블록을 지나가면 옮기는 블록이 그 목록 **안으로 들여써집니다**. 바로 Shift+Tab으로 내어쓰면 같은 단계로 돌아옵니다(↓ 한 번, Shift+Tab 한 번씩 반복).
- 끝나면 Esc로 선택을 풀고, 새로 불러와 순서와 들여쓰기를 다시 확인합니다.

## 끝까지 다시 읽기

Notion은 화면 밖 블록을 그리지 않습니다. 스크롤하며 상위 블록을 모아야 전체를 확인할 수 있습니다.

```js
const sc = document.querySelector('.notion-frame .notion-scroller.vertical');
sc.scrollTop = 0; await new Promise(r => setTimeout(r, 500));
const seen = new Map();
for (let i = 0; i < 40; i++) {
  document.querySelectorAll('.notion-page-content [data-block-id]').forEach(b => {
    if (!b.parentElement.closest('.notion-page-content [data-block-id]') && !seen.has(b.dataset.blockId))
      seen.set(b.dataset.blockId, (b.className.match(/notion-([a-z_]+)-block/) || [])[1] + ' ' + b.innerText.slice(0, 40));
  });
  const before = sc.scrollTop; sc.scrollTop += 400;
  await new Promise(r => setTimeout(r, 300));
  if (sc.scrollTop === before) break;
}
[...seen.values()];
```

모은 순서가 실제 순서와 어긋날 수 있으므로, 순서가 중요하면 화면 확인을 함께 합니다. 두 페이지 내용이 같은지 볼 때도 이 방법으로 양쪽을 모아 줄 단위로 비교합니다.

## 사용자 화면에서 "페이지를 불러오는 중 오류"가 날 때

다른 탭에서 같은 주소를 새로 열어 봅니다. 그 탭에서 정상이면 페이지 문제가 아니라 사용자 탭의 일시 오류입니다(편집 중 열려 있던 탭에서 생긴 적 있음). 새로고침이나 새 탭을 안내합니다.
