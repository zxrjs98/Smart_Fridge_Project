self.addEventListener('install', (e) => {
  console.log('서비스 워커 설치 완료');
  self.skipWaiting(); 
});

self.addEventListener('fetch', (e) => {
  return;
});


// 내 정보 수정 팝업 열기/닫기
function openUserInfo() {
    document.getElementById('userInfoModal').classList.add('show');
    // 사이드바가 열려있다면 닫아줍니다
    document.getElementById('sidebar').classList.remove('active');
    document.getElementById('sidebar-overlay').classList.remove('active');
}

function closeUserInfo() {
    document.getElementById('userInfoModal').classList.remove('show');
}
