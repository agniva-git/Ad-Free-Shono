import { API } from './api.js';
import { player } from './player.js';

// Application State
const state = {
  currentView: 'home',
  viewParams: null,
  cachedSongs: [],
  cachedPlaylists: [],
  isSeeking: false
};

// Utilities
function formatTime(seconds) {
  if (!seconds || isNaN(seconds)) return '0:00';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s < 10 ? '0' : ''}${s}`;
}

// Router & View Loader
export async function navigateTo(view, params = null) {
  state.currentView = view;
  state.viewParams = params;

  // Update nav links
  document.querySelectorAll('.nav-link, .mobile-nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.view === view);
  });

  const contentArea = document.getElementById('content-area');
  contentArea.innerHTML = '<div style="padding: 40px; text-align: center; color: #888;">Loading...</div>';

  switch (view) {
    case 'home':
      await renderHomeView(contentArea);
      break;
    case 'songs':
      await renderSongsView(contentArea);
      break;
    case 'artists':
      await renderArtistsView(contentArea);
      break;
    case 'artist-detail':
      await renderArtistDetailView(contentArea, params);
      break;
    case 'albums':
      await renderAlbumsView(contentArea);
      break;
    case 'album-detail':
      await renderAlbumDetailView(contentArea, params);
      break;
    case 'playlists':
      await renderPlaylistsView(contentArea);
      break;
    case 'playlist-detail':
      await renderPlaylistDetailView(contentArea, params);
      break;
    case 'favorites':
      await renderFavoritesView(contentArea);
      break;
    case 'upload':
      renderUploadView(contentArea);
      break;
    case 'search':
      await renderSearchView(contentArea, params);
      break;
    default:
      await renderHomeView(contentArea);
  }
}

// --- VIEWS ---

async function renderHomeView(container) {
  const [stats, songs, favorites] = await Promise.all([
    API.getStats(),
    API.getSongs({ sort_by: 'created_at', order: 'desc' }),
    API.getSongs({ favorites_only: true })
  ]);

  container.innerHTML = `
    <div class="view-header">
      <div>
        <h2>Welcome to AdFreeShono</h2>
        <p>Your self-hosted, zero-cost personal music library</p>
      </div>
    </div>

    <div style="display: flex; gap: 16px; margin-bottom: 32px; flex-wrap: wrap;">
      <div style="background: var(--bg-card); padding: 16px 24px; border-radius: 8px; flex: 1; min-width: 140px; border: 1px solid var(--border);">
        <div style="font-size: 12px; color: var(--text-muted); text-transform: uppercase;">Total Songs</div>
        <div style="font-size: 24px; font-weight: 700; color: var(--accent); margin-top: 4px;">${stats.total_songs}</div>
      </div>
      <div style="background: var(--bg-card); padding: 16px 24px; border-radius: 8px; flex: 1; min-width: 140px; border: 1px solid var(--border);">
        <div style="font-size: 12px; color: var(--text-muted); text-transform: uppercase;">Artists</div>
        <div style="font-size: 24px; font-weight: 700; margin-top: 4px;">${stats.total_artists}</div>
      </div>
      <div style="background: var(--bg-card); padding: 16px 24px; border-radius: 8px; flex: 1; min-width: 140px; border: 1px solid var(--border);">
        <div style="font-size: 12px; color: var(--text-muted); text-transform: uppercase;">Albums</div>
        <div style="font-size: 24px; font-weight: 700; margin-top: 4px;">${stats.total_albums}</div>
      </div>
      <div style="background: var(--bg-card); padding: 16px 24px; border-radius: 8px; flex: 1; min-width: 140px; border: 1px solid var(--border);">
        <div style="font-size: 12px; color: var(--text-muted); text-transform: uppercase;">Liked Songs</div>
        <div style="font-size: 24px; font-weight: 700; color: #e91e63; margin-top: 4px;">${favorites.length}</div>
      </div>
    </div>

    ${songs.length === 0 ? `
      <div style="text-align: center; padding: 60px 20px; background: var(--bg-card); border-radius: 12px; border: 1px dashed var(--border);">
        <div style="font-size: 40px; margin-bottom: 12px;">🎵</div>
        <h3>Your library is empty</h3>
        <p style="color: var(--text-muted); margin: 8px 0 20px;">Upload music files or scan a folder on your computer to begin streaming.</p>
        <button class="btn" onclick="window.appNavigate('upload')">Go to Upload & Scanner</button>
      </div>
    ` : `
      <div style="margin-bottom: 32px;">
        <h3 style="margin-bottom: 16px; font-size: 20px;">Recently Added</h3>
        <table class="songs-table">
          <thead>
            <tr>
              <th style="width: 40px;">#</th>
              <th>Title</th>
              <th>Artist</th>
              <th>Album</th>
              <th style="width: 80px; text-align: right;">Time</th>
              <th style="width: 40px;"></th>
            </tr>
          </thead>
          <tbody id="home-songs-body"></tbody>
        </table>
      </div>
    `}
  `;

  if (songs.length > 0) {
    const tbody = document.getElementById('home-songs-body');
    renderSongsTableRows(tbody, songs.slice(0, 10), songs);
  }
}

async function renderSongsView(container) {
  const songs = await API.getSongs({ sort_by: 'title' });
  state.cachedSongs = songs;

  container.innerHTML = `
    <div class="view-header">
      <div>
        <h2>All Songs (${songs.length})</h2>
        <p>Complete track catalog</p>
      </div>
      <button class="btn" onclick="window.playAllCachedSongs()">▶ Play All</button>
    </div>

    ${songs.length === 0 ? `
      <p style="color: var(--text-muted);">No songs found. <a href="#" onclick="window.appNavigate('upload'); return false;" style="color: var(--accent);">Upload music</a>.</p>
    ` : `
      <table class="songs-table">
        <thead>
          <tr>
            <th style="width: 40px;">#</th>
            <th>Title</th>
            <th>Artist</th>
            <th>Album</th>
            <th style="width: 80px; text-align: right;">Time</th>
            <th style="width: 80px; text-align: center;">Actions</th>
          </tr>
        </thead>
        <tbody id="all-songs-body"></tbody>
      </table>
    `}
  `;

  if (songs.length > 0) {
    renderSongsTableRows(document.getElementById('all-songs-body'), songs, songs);
  }
}

async function renderFavoritesView(container) {
  const songs = await API.getSongs({ favorites_only: true });

  container.innerHTML = `
    <div class="view-header">
      <div>
        <h2>💖 Liked Songs (${songs.length})</h2>
        <p>Your favorite music</p>
      </div>
      ${songs.length > 0 ? `<button class="btn" onclick="window.playSongList(${JSON.stringify(songs).replace(/"/g, '&quot;')})">▶ Play All</button>` : ''}
    </div>

    ${songs.length === 0 ? `
      <p style="color: var(--text-muted);">No favorites yet. Click the heart icon on any song to save it here.</p>
    ` : `
      <table class="songs-table">
        <thead>
          <tr>
            <th style="width: 40px;">#</th>
            <th>Title</th>
            <th>Artist</th>
            <th>Album</th>
            <th style="width: 80px; text-align: right;">Time</th>
            <th style="width: 40px;"></th>
          </tr>
        </thead>
        <tbody id="favorites-body"></tbody>
      </table>
    `}
  `;

  if (songs.length > 0) {
    renderSongsTableRows(document.getElementById('favorites-body'), songs, songs);
  }
}

async function renderArtistsView(container) {
  const artists = await API.getArtists();

  container.innerHTML = `
    <div class="view-header">
      <div>
        <h2>Artists (${artists.length})</h2>
        <p>Grouped by performer</p>
      </div>
    </div>

    <div class="card-grid">
      ${artists.map(a => `
        <div class="media-card" onclick="window.appNavigate('artist-detail', '${a.id}')">
          <div class="card-cover" style="border-radius: 50%;">🎤</div>
          <h3>${escapeHtml(a.name)}</h3>
          <p>${a.song_count} track${a.song_count === 1 ? '' : 's'}</p>
        </div>
      `).join('')}
    </div>
  `;
}

async function renderArtistDetailView(container, artistId) {
  const data = await API.getArtist(artistId);

  container.innerHTML = `
    <div class="view-header">
      <div>
        <button class="btn-secondary" style="margin-bottom: 12px; padding: 6px 12px; font-size: 12px;" onclick="window.appNavigate('artists')">← Back to Artists</button>
        <h2>${escapeHtml(data.artist.name)}</h2>
        <p>${data.songs.length} tracks</p>
      </div>
      ${data.songs.length > 0 ? `<button class="btn" onclick="window.playSongList(${JSON.stringify(data.songs).replace(/"/g, '&quot;')})">▶ Play All</button>` : ''}
    </div>

    <table class="songs-table">
      <thead>
        <tr>
          <th style="width: 40px;">#</th>
          <th>Title</th>
          <th>Album</th>
          <th style="width: 80px; text-align: right;">Time</th>
          <th style="width: 40px;"></th>
        </tr>
      </thead>
      <tbody id="artist-songs-body"></tbody>
    </table>
  `;

  renderSongsTableRows(document.getElementById('artist-songs-body'), data.songs, data.songs);
}

async function renderAlbumsView(container) {
  const albums = await API.getAlbums();

  container.innerHTML = `
    <div class="view-header">
      <div>
        <h2>Albums (${albums.length})</h2>
        <p>Full album collections</p>
      </div>
    </div>

    <div class="card-grid">
      ${albums.map(al => `
        <div class="media-card" onclick="window.appNavigate('album-detail', '${al.id}')">
          ${al.artwork_path ?
            `<img class="card-cover" src="${al.artwork_path}" alt="Cover"/>` :
            `<div class="card-cover">💿</div>`}
          <h3>${escapeHtml(al.title)}</h3>
          <p>${escapeHtml(al.artist_name || 'Unknown Artist')}</p>
        </div>
      `).join('')}
    </div>
  `;
}

async function renderAlbumDetailView(container, albumId) {
  const data = await API.getAlbum(albumId);

  container.innerHTML = `
    <div class="view-header">
      <div>
        <button class="btn-secondary" style="margin-bottom: 12px; padding: 6px 12px; font-size: 12px;" onclick="window.appNavigate('albums')">← Back to Albums</button>
        <h2>${escapeHtml(data.album.title)}</h2>
        <p>by ${escapeHtml(data.album.artist_name)} • ${data.songs.length} tracks</p>
      </div>
      ${data.songs.length > 0 ? `<button class="btn" onclick="window.playSongList(${JSON.stringify(data.songs).replace(/"/g, '&quot;')})">▶ Play Album</button>` : ''}
    </div>

    <table class="songs-table">
      <thead>
        <tr>
          <th style="width: 40px;">#</th>
          <th>Title</th>
          <th style="width: 80px; text-align: right;">Time</th>
          <th style="width: 40px;"></th>
        </tr>
      </thead>
      <tbody id="album-songs-body"></tbody>
    </table>
  `;

  renderSongsTableRows(document.getElementById('album-songs-body'), data.songs, data.songs);
}

async function renderPlaylistsView(container) {
  const playlists = await API.getPlaylists();
  state.cachedPlaylists = playlists;

  container.innerHTML = `
    <div class="view-header">
      <div>
        <h2>Playlists (${playlists.length})</h2>
        <p>Custom playlists and mixtapes</p>
      </div>
      <button class="btn" onclick="window.promptCreatePlaylist()">+ New Playlist</button>
    </div>

    <div class="card-grid">
      ${playlists.map(p => `
        <div class="media-card" onclick="window.appNavigate('playlist-detail', '${p.id}')">
          <div class="card-cover">📋</div>
          <h3>${escapeHtml(p.name)}</h3>
          <p>${p.song_count} track${p.song_count === 1 ? '' : 's'}</p>
        </div>
      `).join('')}
    </div>
  `;
}

async function renderPlaylistDetailView(container, playlistId) {
  const playlist = await API.getPlaylist(playlistId);

  container.innerHTML = `
    <div class="view-header">
      <div>
        <button class="btn-secondary" style="margin-bottom: 12px; padding: 6px 12px; font-size: 12px;" onclick="window.appNavigate('playlists')">← Back to Playlists</button>
        <h2>${escapeHtml(playlist.name)}</h2>
        <p>${playlist.description || ''} • ${playlist.song_count} tracks</p>
      </div>
      <div style="display: flex; gap: 8px;">
        ${playlist.songs.length > 0 ? `<button class="btn" onclick="window.playSongList(${JSON.stringify(playlist.songs).replace(/"/g, '&quot;')})">▶ Play All</button>` : ''}
        <button class="btn-secondary" onclick="window.confirmDeletePlaylist('${playlist.id}')">Delete Playlist</button>
      </div>
    </div>

    ${playlist.songs.length === 0 ? `
      <p style="color: var(--text-muted);">This playlist is empty. Add songs from the library using the '+' button on tracks.</p>
    ` : `
      <table class="songs-table">
        <thead>
          <tr>
            <th style="width: 40px;">#</th>
            <th>Title</th>
            <th>Artist</th>
            <th>Album</th>
            <th style="width: 80px; text-align: right;">Time</th>
            <th style="width: 40px;"></th>
          </tr>
        </thead>
        <tbody id="playlist-songs-body"></tbody>
      </table>
    `}
  `;

  if (playlist.songs.length > 0) {
    renderSongsTableRows(document.getElementById('playlist-songs-body'), playlist.songs, playlist.songs);
  }
}

async function renderSearchView(container, query) {
  if (!query) {
    container.innerHTML = `<h2>Search</h2><p style="color: var(--text-muted);">Type in the search bar above to find songs, artists, and albums.</p>`;
    return;
  }

  const results = await API.search(query);

  container.innerHTML = `
    <div class="view-header">
      <div>
        <h2>Search results for "${escapeHtml(query)}"</h2>
        <p>Found ${results.songs.length} songs, ${results.artists.length} artists, ${results.albums.length} albums</p>
      </div>
    </div>

    ${results.songs.length > 0 ? `
      <h3 style="margin: 24px 0 12px;">Songs</h3>
      <table class="songs-table">
        <tbody id="search-songs-body"></tbody>
      </table>
    ` : ''}

    ${results.artists.length > 0 ? `
      <h3 style="margin: 32px 0 16px;">Artists</h3>
      <div class="card-grid">
        ${results.artists.map(a => `
          <div class="media-card" onclick="window.appNavigate('artist-detail', '${a.id}')">
            <div class="card-cover" style="border-radius: 50%;">🎤</div>
            <h3>${escapeHtml(a.name)}</h3>
            <p>${a.song_count} track${a.song_count === 1 ? '' : 's'}</p>
          </div>
        `).join('')}
      </div>
    ` : ''}

    ${results.songs.length === 0 && results.artists.length === 0 && results.albums.length === 0 ? `
      <p style="color: var(--text-muted); margin-top: 20px;">No results found matching "${escapeHtml(query)}".</p>
    ` : ''}
  `;

  if (results.songs.length > 0) {
    renderSongsTableRows(document.getElementById('search-songs-body'), results.songs, results.songs);
  }
}

function renderUploadView(container) {
  container.innerHTML = `
    <div class="view-header">
      <div>
        <h2>Upload & Library Scanner</h2>
        <p>Zero-cost ingestion: add files individually or scan an existing directory</p>
      </div>
    </div>

    <!-- Drag and Drop Upload -->
    <div class="upload-dropzone" id="dropzone" onclick="document.getElementById('file-input').click()">
      <div class="upload-icon">☁️</div>
      <h3>Drag & drop audio files here</h3>
      <p style="color: var(--text-muted); margin-top: 8px;">Supports MP3, FLAC, M4A, AAC, OGG, WAV</p>
      <input type="file" id="file-input" multiple accept="audio/*" style="display: none;" />
      <div id="upload-status" style="margin-top: 16px; font-weight: 600; color: var(--accent);"></div>
    </div>

    <!-- Scanner Box -->
    <div class="scan-box">
      <h3 style="margin-bottom: 8px;">📂 Scan Existing Music Folder on PC</h3>
      <p style="color: var(--text-muted); font-size: 13px; margin-bottom: 16px;">
        Have an existing folder of music on your hard drive? Point the scanner at it and it will automatically index all tags and cover artwork into your SQLite database without uploading.
      </p>
      <div style="display: flex; gap: 12px; max-width: 600px;">
        <input type="text" id="scan-path-input" placeholder="e.g. D:\\Music or leave empty for configured data/media" style="flex: 1; padding: 10px 14px; background: var(--bg-main); border: 1px solid var(--border); border-radius: 8px; color: #fff; font-size: 13px;" />
        <button class="btn" id="scan-btn" onclick="window.handleDirectoryScan()">Scan Folder</button>
      </div>
      <div id="scan-result" style="margin-top: 14px; font-size: 13px;"></div>
    </div>
  `;

  // Attach drag-drop events
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('file-input');

  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  });

  dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('dragover');
  });

  dropzone.addEventListener('drop', async (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
      await handleFilesUpload(e.dataTransfer.files);
    }
  });

  fileInput.addEventListener('change', async () => {
    if (fileInput.files.length > 0) {
      await handleFilesUpload(fileInput.files);
    }
  });
}

// Helpers
function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renderSongsTableRows(tbody, songsToRender, parentList) {
  tbody.innerHTML = songsToRender.map((song, idx) => {
    const isPlayingThis = player.currentTrack?.id === song.id;
    return `
      <tr class="${isPlayingThis ? 'playing' : ''}" data-song-id="${song.id}">
        <td style="color: var(--text-muted); font-size: 12px;" onclick="window.playSongFromList('${song.id}')">${idx + 1}</td>
        <td onclick="window.playSongFromList('${song.id}')">
          <div class="song-title-cell">
            ${song.artwork_url ?
              `<img src="${song.artwork_url}" class="song-thumb" alt="cover"/>` :
              `<div class="song-thumb">🎵</div>`}
            <div class="song-meta">
              <h4>${escapeHtml(song.title)}</h4>
              <span>${escapeHtml(song.artist_name || 'Unknown')}</span>
            </div>
          </div>
        </td>
        <td onclick="window.playSongFromList('${song.id}')" style="color: var(--text-muted);">${escapeHtml(song.artist_name || 'Unknown')}</td>
        <td onclick="window.playSongFromList('${song.id}')" style="color: var(--text-muted);">${escapeHtml(song.album_title || 'Unknown')}</td>
        <td onclick="window.playSongFromList('${song.id}')" style="text-align: right; color: var(--text-muted);">${formatTime(song.duration_seconds)}</td>
        <td style="text-align: center;">
          <button class="heart-btn ${song.is_favorite ? 'active' : ''}" title="Favorite" onclick="event.stopPropagation(); window.toggleSongFavorite('${song.id}', this)">
            ${song.is_favorite ? '❤️' : '🤍'}
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

async function handleFilesUpload(files) {
  const statusEl = document.getElementById('upload-status');
  statusEl.innerText = `Uploading ${files.length} file(s)...`;

  let successCount = 0;
  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    statusEl.innerText = `Uploading (${i + 1}/${files.length}): ${file.name}...`;
    const fd = new FormData();
    fd.append('file', file);
    try {
      await API.uploadSong(fd);
      successCount++;
    } catch (e) {
      console.error('Upload error', e);
    }
  }

  statusEl.innerText = `✅ Successfully uploaded ${successCount} track(s)!`;
  setTimeout(() => {
    navigateTo('songs');
  }, 1200);
}

// Window Globals for UI bindings
window.appNavigate = navigateTo;

window.playSongFromList = function(songId) {
  const song = state.cachedSongs.find(s => s.id === songId);
  if (song) {
    player.playTrack(song, state.cachedSongs);
  } else {
    API.getSong(songId).then(s => player.playTrack(s));
  }
};

window.playAllCachedSongs = function() {
  if (state.cachedSongs.length > 0) {
    player.playTrack(state.cachedSongs[0], state.cachedSongs);
  }
};

window.playSongList = function(list) {
  if (list && list.length > 0) {
    player.playTrack(list[0], list);
  }
};

window.toggleSongFavorite = async function(songId, btnEl) {
  const res = await API.toggleFavorite(songId);
  if (res.is_favorite) {
    btnEl.classList.add('active');
    btnEl.innerText = '❤️';
  } else {
    btnEl.classList.remove('active');
    btnEl.innerText = '🤍';
  }
};

window.promptCreatePlaylist = async function() {
  const name = prompt('Enter playlist name:');
  if (name && name.trim()) {
    await API.createPlaylist(name.trim());
    navigateTo('playlists');
  }
};

window.confirmDeletePlaylist = async function(playlistId) {
  if (confirm('Delete this playlist?')) {
    await API.deletePlaylist(playlistId);
    navigateTo('playlists');
  }
};

window.handleDirectoryScan = async function() {
  const input = document.getElementById('scan-path-input');
  const resultEl = document.getElementById('scan-result');
  const btn = document.getElementById('scan-btn');

  btn.disabled = true;
  resultEl.style.color = '#888';
  resultEl.innerText = 'Scanning folder and parsing audio metadata...';

  try {
    const path = input.value.trim() || null;
    const res = await API.triggerScan(path, false);
    resultEl.style.color = 'var(--accent)';
    resultEl.innerText = `✅ Scan complete! Scanned: ${res.scanned}, Newly Added: ${res.added}, Skipped (already indexed): ${res.skipped}`;
  } catch (e) {
    resultEl.style.color = '#ff5252';
    resultEl.innerText = `Error scanning folder: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
};

// Player UI synchronization
function setupPlayerUI() {
  const playPauseBtn = document.getElementById('play-pause-btn');
  const prevBtn = document.getElementById('prev-btn');
  const nextBtn = document.getElementById('next-btn');
  const shuffleBtn = document.getElementById('shuffle-btn');
  const repeatBtn = document.getElementById('repeat-btn');
  const progressSlider = document.getElementById('progress-slider');
  const volumeSlider = document.getElementById('volume-slider');
  const currentTimeEl = document.getElementById('current-time');
  const totalTimeEl = document.getElementById('total-time');
  const coverImg = document.getElementById('player-cover-img');
  const titleEl = document.getElementById('player-title');
  const artistEl = document.getElementById('player-artist');

  playPauseBtn.addEventListener('click', () => player.togglePlayPause());
  prevBtn.addEventListener('click', () => player.prev());
  nextBtn.addEventListener('click', () => player.next());
  shuffleBtn.addEventListener('click', () => player.toggleShuffle());
  repeatBtn.addEventListener('click', () => player.toggleRepeat());

  progressSlider.addEventListener('mousedown', () => { state.isSeeking = true; });
  progressSlider.addEventListener('touchstart', () => { state.isSeeking = true; });
  progressSlider.addEventListener('change', () => {
    player.seek(parseFloat(progressSlider.value));
    state.isSeeking = false;
  });
  progressSlider.addEventListener('input', () => {
    currentTimeEl.innerText = formatTime(parseFloat(progressSlider.value));
  });

  volumeSlider.addEventListener('input', (e) => {
    player.setVolume(parseFloat(e.target.value));
  });

  player.subscribe((type, data) => {
    if (type === 'state') {
      playPauseBtn.innerHTML = data.isPlaying ? '⏸' : '▶';
      shuffleBtn.classList.toggle('active', data.isShuffle);
      repeatBtn.classList.toggle('active', data.repeatMode !== 'off');

      if (data.track) {
        titleEl.innerText = data.track.title;
        artistEl.innerText = data.track.artist_name || 'Unknown Artist';
        if (data.track.artwork_url) {
          coverImg.innerHTML = `<img src="${data.track.artwork_url}" style="width:100%; height:100%; border-radius:6px; object-fit:cover;" />`;
        } else {
          coverImg.innerHTML = '🎵';
        }
      }

      // Highlight playing row in current table
      document.querySelectorAll('.songs-table tr').forEach(row => {
        row.classList.toggle('playing', row.dataset.songId === data.track?.id);
      });
    } else if (type === 'progress') {
      if (!state.isSeeking) {
        progressSlider.max = data.duration || 100;
        progressSlider.value = data.currentTime || 0;
        currentTimeEl.innerText = formatTime(data.currentTime);
        totalTimeEl.innerText = formatTime(data.duration);
      }
    }
  });
}

// Search bar input
function setupSearchInput() {
  const input = document.getElementById('global-search');
  let timeout = null;
  input.addEventListener('input', () => {
    clearTimeout(timeout);
    timeout = setTimeout(() => {
      const q = input.value.trim();
      if (q) {
        navigateTo('search', q);
      } else if (state.currentView === 'search') {
        navigateTo('home');
      }
    }, 300);
  });
}

// Service Worker registration
function registerSW() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(e => console.log('SW registration skipped', e));
  }
}

// Application Init
document.addEventListener('DOMContentLoaded', () => {
  setupPlayerUI();
  setupSearchInput();
  registerSW();
  navigateTo('home');
});
