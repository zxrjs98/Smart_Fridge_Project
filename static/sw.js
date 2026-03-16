self.addEventListener('install', (e) => {
  console.log('서비스 워커 설치 완료!');
  self.skipWaiting(); // 설치 즉시 활성화
});

self.addEventListener('fetch', (e) => {
  // 아무것도 하지 않고 네트워크 요청을 그대로 내보냄
  return;
});