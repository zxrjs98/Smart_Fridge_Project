self.addEventListener('install', (e) => {
  console.log('서비스 워커 설치 완료!');
});

self.addEventListener('fetch', (e) => {
  // 네트워크 요청을 가로채서 처리하는 곳 (지금은 통과시킵니다)
});