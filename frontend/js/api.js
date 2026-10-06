const API_BASE = '/api';

export const API = {
  async getSongs(params = {}) {
    const query = new URLSearchParams(params).toString();
    const res = await fetch(`${API_BASE}/songs?${query}`);
    return res.json();
  },

  async getSong(id) {
    const res = await fetch(`${API_BASE}/songs/${id}`);
    return res.json();
  },

  getStreamUrl(id) {
    return `${API_BASE}/songs/${id}/stream`;
  },

  async updateSong(id, data) {
    const res = await fetch(`${API_BASE}/songs/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    return res.json();
  },

  async deleteSong(id) {
    const res = await fetch(`${API_BASE}/songs/${id}`, { method: 'DELETE' });
    return res.json();
  },

  async toggleFavorite(id) {
    const res = await fetch(`${API_BASE}/songs/${id}/favorite`, { method: 'POST' });
    return res.json();
  },

  async getRecentlyPlayed() {
    const res = await fetch(`${API_BASE}/songs/history/recent`);
    return res.json();
  },

  async recordHistory(id) {
    try {
      await fetch(`${API_BASE}/songs/${id}/history`, { method: 'POST' });
    } catch (e) {
      // Non-critical
    }
  },

  async getArtists() {
    const res = await fetch(`${API_BASE}/artists`);
    return res.json();
  },

  async getArtist(id) {
    const res = await fetch(`${API_BASE}/artists/${id}`);
    return res.json();
  },

  async getAlbums() {
    const res = await fetch(`${API_BASE}/albums`);
    return res.json();
  },

  async getAlbum(id) {
    const res = await fetch(`${API_BASE}/albums/${id}`);
    return res.json();
  },

  async getPlaylists() {
    const res = await fetch(`${API_BASE}/playlists`);
    return res.json();
  },

  async createPlaylist(name, description = '') {
    const res = await fetch(`${API_BASE}/playlists`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, description })
    });
    return res.json();
  },

  async getPlaylist(id) {
    const res = await fetch(`${API_BASE}/playlists/${id}`);
    return res.json();
  },

  async deletePlaylist(id) {
    const res = await fetch(`${API_BASE}/playlists/${id}`, { method: 'DELETE' });
    return res.json();
  },

  async addSongToPlaylist(playlistId, songId) {
    const res = await fetch(`${API_BASE}/playlists/${playlistId}/songs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ song_id: songId })
    });
    return res.json();
  },

  async removeSongFromPlaylist(playlistId, songId) {
    const res = await fetch(`${API_BASE}/playlists/${playlistId}/songs/${songId}`, {
      method: 'DELETE'
    });
    return res.json();
  },

  async search(q) {
    const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(q)}`);
    return res.json();
  },

  async getStats() {
    const res = await fetch(`${API_BASE}/stats`);
    return res.json();
  },

  async uploadSong(formData) {
    const res = await fetch(`${API_BASE}/upload`, {
      method: 'POST',
      body: formData
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Upload failed');
    }
    return res.json();
  },

  async triggerScan(directoryPath = null, copyToStorage = false) {
    const res = await fetch(`${API_BASE}/scan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ directory_path: directoryPath, copy_to_storage: copyToStorage })
    });
    return res.json();
  }
};
