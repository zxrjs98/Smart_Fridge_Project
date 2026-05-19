// 서비스 워커 설치 및 활성화 세팅
self.addEventListener('install', (e) => {
  console.log('서비스 워커 설치 완료');
  self.skipWaiting(); 
});

self.addEventListener('fetch', (e) => {
  return;
});

// 백그라운드에서 푸시 이벤트를 수신했을 때 실행되는 로직
self.addEventListener('push', function(event) {
    let data = { title: 'Smart Fridge 소비기한 알림', body: '임박한 식재료가 있습니다!' };
    
    if (event.data) {
        try {
            data = event.data.json();
        } catch (e) {
            data.body = event.data.text();
        }
    }

    const options = {
        body: data.body,
        icon: '/static/images/fresh.png', // 프로젝트 로고 경로에 맞게 수정
        badge: '/static/images/fresh_ico.png',
        vibrate: [100, 50, 100],
        data: {
            dateOfArrival: Date.now(),
            primaryKey: '2'
        }
    };

    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});

self.addEventListener('notificationclick', function(event) {
    // 1. 클릭된 알림창을 화면에서 즉시 닫아줍니다.
    event.notification.close();

    // 2. 현재 브라우저 탭이나 PWA 창이 열려있는지 확인하고 제어합니다.
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true })
        .then(function(clientList) {
            // 이미 앱이 켜져 있다면 해당 창을 포커스(활성화)합니다.
            for (let i = 0; i < clientList.length; i++) {
                let client = clientList[i];
                if ('focus' in client) {
                    return client.focus();
                }
            }
            
            // 만약 앱이 완전히 닫혀 있다면 ngrok 주소(메인 페이지)로 새 창을 열어줍니다.
            if (clients.openWindow) {
                // '/'를 넣으면 서비스 워커가 구동 중인 최상위 루트 경로(메인 페이지)가 열립니다.
                return clients.openWindow('/'); 
            }
        })
    );
});