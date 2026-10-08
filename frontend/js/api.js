const BASE = '/api';

export class AuthError extends Error {}

async function request(path, options = {}) {
  const res = await fetch(BASE + path, options);
  if (res.status === 401) throw new AuthError('Login required');
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* body was not JSON */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return res.json();
}

const send = (method, body) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export const API = {
  authStatus: () => request('/auth/status'),
  login: (password) => request('/login', send('POST', { password })),
  logout: () => request('/logout', { method: 'POST' }),

  getSongs: (params = {}) => request('/songs?' + new URLSearchParams(params)),
  getSong: (id) => request(`/songs/${id}`),
  getStreamUrl: (id) => `${BASE}/songs/${id}/stream`,
  updateSong: (id, data) => request(`/songs/${id}`, send('PATCH', data)),
  deleteSong: (id) => request(`/songs/${id}`, { method: 'DELETE' }),
  toggleFavorite: (id) => request(`/songs/${id}/favorite`, { method: 'POST' }),
  getRecentlyPlayed: () => request('/songs/history/recent'),
  recordHistory: (id) => request(`/songs/${id}/history`, { method: 'POST' }).catch(() => {}),

  getArtists: () => request('/artists'),
  getArtist: (id) => request(`/artists/${id}`),
  getAlbums: () => request('/albums'),
  getAlbum: (id) => request(`/albums/${id}`),

  getPlaylists: () => request('/playlists'),
  getPlaylist: (id) => request(`/playlists/${id}`),
  createPlaylist: (name, description = '') => request('/playlists', send('POST', { name, description })),
  deletePlaylist: (id) => request(`/playlists/${id}`, { method: 'DELETE' }),
  addSongToPlaylist: (pid, sid) => request(`/playlists/${pid}/songs`, send('POST', { song_id: sid })),
  removeSongFromPlaylist: (pid, sid) => request(`/playlists/${pid}/songs/${sid}`, { method: 'DELETE' }),

  search: (q) => request('/search?q=' + encodeURIComponent(q)),
  getStats: () => request('/stats'),
  uploadSong: (formData) => request('/upload', { method: 'POST', body: formData }),
  triggerScan: (directoryPath = null, copyToStorage = false) =>
    request('/scan', send('POST', { directory_path: directoryPath, copy_to_storage: copyToStorage })),
};
