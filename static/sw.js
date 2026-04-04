self.addEventListener('install', (e) => {
  console.log('서비스 워커 설치 완료');
  self.skipWaiting(); 
});

self.addEventListener('fetch', (e) => {
  return;
});