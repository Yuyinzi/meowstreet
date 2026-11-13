export function createNotificationFeed({ request, onSnapshot, onEvents, onError, onUnread }) {
  let cursor = null;
  let busy = false;
  let version = 0;
  return {
    invalidate() { version++; },
    async tick() {
      if (busy) return;
      busy = true;
      const requestVersion = version;
      try {
        if (cursor === null) {
          const snapshot = await request('/api/notifications');
          if (requestVersion !== version) return;
          onSnapshot(snapshot);
          cursor = snapshot.next_cursor;
          onUnread(snapshot.unread_count);
          return;
        }
        for (let page = 0; page < 10; page++) {
          const payload = await request(`/api/notifications/events?after=${cursor}`);
          if (requestVersion !== version) return;
          onEvents(payload.events, payload);
          cursor = payload.next_cursor;
          onUnread(payload.unread_count);
          if (!payload.has_more) break;
        }
      } catch (error) {
        if (requestVersion === version) onError(error);
      } finally {
        busy = false;
      }
    },
  };
}
