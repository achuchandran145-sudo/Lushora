/* LUSHORA Firebase Messaging service worker. */
importScripts('https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.14.1/firebase-messaging-compat.js');

const configParam = new URL(self.location.href).searchParams.get('config');
let firebaseConfig = {};
try { firebaseConfig = configParam ? JSON.parse(configParam) : {}; } catch (_) { firebaseConfig = {}; }
if (firebaseConfig && firebaseConfig.apiKey) {
  firebase.initializeApp(firebaseConfig);
  const messaging = firebase.messaging();
  messaging.onBackgroundMessage((payload) => {
    const title = payload.notification?.title || 'LUSHORA';
    self.registration.showNotification(title, {
      body: payload.notification?.body || 'You have a new booking update.',
      icon: '/favicon.ico',
      data: payload.data || {}
    });
  });
}
