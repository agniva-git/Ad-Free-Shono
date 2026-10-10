import { API, AuthError } from './api.js';
import { player } from './player.js';

const $ = (sel) => document.querySelector(sel);
const view = $('#view');
const modal = $('#modal');

// lists: song arrays currently on screen, so a row click can play "this list from here"
const state = { nav: 0, route: 'home', lists: {}, seeking: false, user: null };

/* ---------- helpers ---------- */

const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function fmt(sec) {
  if (!sec || Number.isNaN(sec)) return '0:00';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

function fmtLong(sec) {
  const t = Math.round(sec || 0);
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  return `${h}:${String(m).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`;
}

let statusTimer;
function setStatus(msg, isError = false) {
  const el = $('#status');
  el.textContent = msg;
  el.className = isError ? 'error' : '';
  clearTimeout(statusTimer);
  if (msg) statusTimer = setTimeout(() => { el.textContent = ''; }, 4000);
}

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
const head = (title, actions = '') =>
  `<div class="head"><h1>${esc(title)}</h1><div class="actions">${actions}</div></div>`;
const playAll = (list, label = 'Play all') =>
  `<button data-action="play-all" data-list="${list}">${label}</button>`;
const empty = (msg) => `<p class="dim">${msg}</p>`;

function card(href, imgUrl, placeholder, name, meta) {
  const cover = imgUrl
    ? `<img class="cover" src="${esc(imgUrl)}" alt="" loading="lazy">`
    : `<div class="cover">${placeholder}</div>`;
  return `<a class="card" href="${href}">${cover}<div class="name">${esc(name)}</div><div class="meta">${esc(meta)}</div></a>`;
}

function songTable(songs, list, { artist = true, album = true, playlistId = null } = {}) {
  state.lists[list] = songs;
  const playingId = player.currentTrack?.id;

  const rows = songs.map((s, i) => {
    const play = `data-action="play" data-list="${list}" data-i="${i}"`;
    const id = esc(s.id);
    const fav = `<button data-action="fav" data-id="${id}" title="Like / unlike" aria-label="Like or unlike">${s.is_favorite ? '[*]' : '[ ]'}</button>`;
    const owner = s.can_edit
      ? `<button data-action="edit" data-id="${id}" title="Edit details" aria-label="Edit details">[e]</button>
         <button data-action="delete" data-id="${id}" title="Delete" aria-label="Delete">[x]</button>`
      : '';
    const tools = playlistId
      ? `<button data-action="pl-remove" data-pl="${esc(playlistId)}" data-id="${id}" title="Remove from playlist" aria-label="Remove from playlist">[-]</button>`
      : `<button data-action="pl-add" data-id="${id}" title="Add to playlist" aria-label="Add to playlist">[+]</button>${owner}`;
    return `<tr data-id="${id}"${s.id === playingId ? ' class="playing"' : ''}>
      <td class="n" ${play}>${i + 1}</td>
      <td class="t" ${play}>${esc(s.title)}<span class="sub">${esc(s.artist_name)}</span></td>
      ${artist ? `<td class="c-artist" ${play}>${esc(s.artist_name)}</td>` : ''}
      ${album ? `<td class="c-album" ${play}>${esc(s.album_title)}</td>` : ''}
      <td class="time" ${play}>${fmt(s.duration_seconds)}</td>
      <td class="acts">${fav} ${tools}</td>
    </tr>`;
  }).join('');

  return `<table class="songs">
    <thead><tr>
      <th class="n">#</th><th>Title</th>
      ${artist ? '<th class="c-artist">Artist</th>' : ''}
      ${album ? '<th class="c-album">Album</th>' : ''}
      <th class="time">Time</th><th></th>
    </tr></thead>
    <tbody>${rows}</tbody></table>`;
}

/* ---------- views: each returns { html, after? } ---------- */

async function viewHome() {
  const [stats, added, liked, recent] = await Promise.all([
    API.getStats(),
    API.getSongs({ sort_by: 'created_at', order: 'desc' }),
    API.getSongs({ favorites_only: true }),
    API.getRecentlyPlayed(),
  ]);

  const readout = `<div class="readout">
    <span>SONGS <b>${stats.total_songs}</b></span>
    <span>ARTISTS <b>${stats.total_artists}</b></span>
    <span>ALBUMS <b>${stats.total_albums}</b></span>
    <span>PLAYLISTS <b>${stats.total_playlists}</b></span>
    <span>LIKED <b>${liked.length}</b></span>
    <span>TOTAL TIME <b>${fmtLong(stats.total_duration_seconds)}</b></span>
  </div>`;

  if (stats.total_songs === 0) {
    return { html: head('Home') + readout +
      `<div class="box"><p>The library is empty.</p>
       <p class="dim">Upload audio files, or point the scanner at a folder on this computer.</p>
       <a href="#/upload"><button>Go to upload</button></a></div>` };
  }

  const recentTop = recent.slice(0, 10);
  const addedTop = added.slice(0, 10);
  return { html: head('Home') + readout +
    (recentTop.length
      ? `<h2>Recently played</h2>${songTable(recentTop, 'recent')}` : '') +
    `<h2>Recently added</h2>${songTable(addedTop, 'added')}` };
}

async function viewSongs() {
  const songs = await API.getSongs({ sort_by: 'title' });
  return { html: head(`All songs (${songs.length})`, songs.length ? playAll('all') : '') +
    (songs.length ? songTable(songs, 'all') : empty('No songs yet. <a href="#/upload">Upload some</a>.')) };
}

async function viewLiked() {
  const songs = await API.getSongs({ favorites_only: true });
  return { html: head(`Liked songs (${songs.length})`, songs.length ? playAll('liked') : '') +
    (songs.length ? songTable(songs, 'liked') : empty('Nothing liked yet. Use [ ] on any song.')) };
}

async function viewArtists() {
  const artists = await API.getArtists();
  return { html: head(`Artists (${artists.length})`) +
    (artists.length
      ? `<div class="grid">${artists.map((a) =>
          card(`#/artist/${a.id}`, a.artwork_path, 'NO IMG', a.name, plural(a.song_count, 'track'))).join('')}</div>`
      : empty('No artists yet.')) };
}

async function viewArtist(id) {
  const d = await API.getArtist(id);
  return { html:
    `<p><a href="#/artists">&lt; Artists</a></p>` +
    head(d.artist.name, d.songs.length ? playAll('artist') : '') +
    `<p class="dim">${plural(d.songs.length, 'track')}</p>` +
    songTable(d.songs, 'artist', { artist: false }) };
}

async function viewAlbums() {
  const albums = await API.getAlbums();
  return { html: head(`Albums (${albums.length})`) +
    (albums.length
      ? `<div class="grid">${albums.map((al) =>
          card(`#/album/${al.id}`, al.artwork_path, 'NO ART', al.title, al.artist_name || 'Unknown Artist')).join('')}</div>`
      : empty('No albums yet.')) };
}

async function viewAlbum(id) {
  const d = await API.getAlbum(id);
  return { html:
    `<p><a href="#/albums">&lt; Albums</a></p>` +
    head(d.album.title, d.songs.length ? playAll('album', 'Play album') : '') +
    `<p class="dim">by ${esc(d.album.artist_name)} / ${plural(d.songs.length, 'track')}</p>` +
    songTable(d.songs, 'album', { album: false }) };
}

async function viewPlaylists() {
  const playlists = await API.getPlaylists();
  return { html: head(`Playlists (${playlists.length})`, '<button data-action="pl-new">New playlist</button>') +
    (playlists.length
      ? `<div class="grid">${playlists.map((p) =>
          card(`#/playlist/${p.id}`, null, 'PLAYLIST', p.name, plural(p.song_count, 'track'))).join('')}</div>`
      : empty('No playlists yet. Playlists are private: only you can see yours.')) };
}

async function viewPlaylist(id) {
  const p = await API.getPlaylist(id);
  const actions = (p.songs.length ? playAll('playlist') : '') +
    `<button data-action="pl-delete" data-pl="${esc(p.id)}">Delete playlist</button>`;
  return { html:
    `<p><a href="#/playlists">&lt; Playlists</a></p>` +
    head(p.name, actions) +
    `<p class="dim">${esc(p.description || '')} ${plural(p.song_count, 'track')}</p>` +
    (p.songs.length
      ? songTable(p.songs, 'playlist', { playlistId: p.id })
      : empty('This playlist is empty. Use [+] on any song to add it.')) };
}

async function viewSearch(q) {
  if (!q) return { html: head('Search') + empty('Type in the search box above.') };
  const r = await API.search(q);
  const none = !r.songs.length && !r.artists.length && !r.albums.length;
  return { html:
    head(`Search: ${q}`) +
    `<p class="dim">${plural(r.songs.length, 'song')}, ${plural(r.artists.length, 'artist')}, ${plural(r.albums.length, 'album')}</p>` +
    (r.songs.length ? `<h2>Songs</h2>${songTable(r.songs, 'search')}` : '') +
    (r.artists.length
      ? `<h2>Artists</h2><div class="grid">${r.artists.map((a) =>
          card(`#/artist/${a.id}`, a.artwork_path, 'NO IMG', a.name, plural(a.song_count, 'track'))).join('')}</div>` : '') +
    (r.albums.length
      ? `<h2>Albums</h2><div class="grid">${r.albums.map((al) =>
          card(`#/album/${al.id}`, al.artwork_path, 'NO ART', al.title, al.artist_name || 'Unknown Artist')).join('')}</div>` : '') +
    (none ? empty('Nothing found.') : '') };
}

function viewUpload() {
  const html = head('Upload and scan') +
    `<div class="drop" id="drop">Drop audio files here, or click to browse
       <div class="dim">MP3 FLAC M4A AAC OGG OPUS WAV</div>
       <div class="dim">Songs you upload are shared with everyone who has an account.</div>
       <input type="file" id="file-input" accept="audio/*" multiple hidden>
     </div>
     <div id="upload-out" class="box" hidden></div>

     <div class="box">
       <h2>Override tags (one file only)</h2>
       <p class="dim">Used only when you upload a single file with missing or wrong tags.</p>
       <label class="field"><span>Title</span><input id="m-title"></label>
       <label class="field"><span>Artist</span><input id="m-artist"></label>
       <label class="field"><span>Album</span><input id="m-album"></label>
       <label class="field"><span>Genre</span><input id="m-genre"></label>
     </div>

     ${state.user?.role === 'admin' ? `<div class="box">
       <h2>Scan a folder on the server</h2>
       <p class="dim">Songs are indexed where they are. Nothing is copied, and deleting a song here never deletes the file.</p>
       <div class="row">
         <input id="scan-path" placeholder="/music   (empty = the app's own audio folder)">
         <button id="scan-btn" data-action="scan">Scan folder</button>
       </div>
       <p id="scan-out" style="margin-top:10px"></p>
     </div>` : ''}`;

  const after = () => {
    const drop = $('#drop');
    const input = $('#file-input');
    drop.addEventListener('click', (e) => { if (e.target !== input) input.click(); });
    drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
    drop.addEventListener('dragleave', () => drop.classList.remove('over'));
    drop.addEventListener('drop', (e) => {
      e.preventDefault();
      drop.classList.remove('over');
      if (e.dataTransfer.files.length) uploadFiles([...e.dataTransfer.files]);
    });
    input.addEventListener('change', () => { if (input.files.length) uploadFiles([...input.files]); });
  };
  return { html, after };
}

async function viewAdmin() {
  if (state.user?.role !== 'admin') return { html: head('Admin') + '<p class="error">Admins only.</p>' };
  const users = await API.adminUsers();
  const rows = users.map((u) => `<tr>
      <td>${esc(u.username)}</td><td>${esc(u.role)}</td>
      <td class="${u.is_active ? '' : 'error'}">${u.is_active ? 'active' : 'DISABLED'}</td>
      <td class="time">${u.upload_count}</td>
      <td class="acts">
        <button data-action="user-pw" data-id="${esc(u.id)}" data-name="${esc(u.username)}">Reset password</button>
        ${u.id === state.user.id ? '' : `<button data-action="user-toggle" data-id="${esc(u.id)}" data-active="${u.is_active}">${u.is_active ? 'Disable' : 'Enable'}</button>`}
      </td></tr>`).join('');
  return { html: head(`Accounts (${users.length})`) +
    `<div class="box">
       <h2>Add a friend</h2>
       <p class="dim">They can listen, upload, and keep private playlists and likes. Only admins can scan folders or manage accounts. Send them the username and password privately.</p>
       <label class="field"><span>Username (letters, numbers, . _ -)</span><input id="nu-name" autocomplete="off"></label>
       <label class="field"><span>Password (10+ characters)</span><input id="nu-pw" autocomplete="off"></label>
       <label class="field"><span>Role</span><select id="nu-role"><option value="member">friend</option><option value="admin">admin</option></select></label>
       <button data-action="user-create">Create account</button>
       <p id="nu-msg" class="error" style="margin-top:10px"></p>
     </div>
     <table class="songs">
       <thead><tr><th>Username</th><th>Role</th><th>Status</th><th class="time">Uploads</th><th></th></tr></thead>
       <tbody>${rows}</tbody></table>` };
}

/* ---------- router ---------- */

const routes = {
  home: viewHome, songs: viewSongs, liked: viewLiked,
  artists: viewArtists, artist: viewArtist,
  albums: viewAlbums, album: viewAlbum,
  playlists: viewPlaylists, playlist: viewPlaylist,
  search: viewSearch, upload: viewUpload, admin: viewAdmin,
};
const NAV_OF = { artist: 'artists', album: 'albums', playlist: 'playlists' };

async function route(quiet = false) {
  const token = ++state.nav;
  const [name, ...rest] = location.hash.replace(/^#\/?/, '').split('/');
  const arg = rest.length ? decodeURIComponent(rest.join('/')) : null;
  const key = routes[name] ? name : 'home';
  state.route = key;

  document.querySelectorAll('#nav a').forEach((a) =>
    a.classList.toggle('active', a.dataset.route === (NAV_OF[key] || key)));
  const search = $('#search');
  if (key === 'search') { if (search.value.trim() !== arg) search.value = arg || ''; }
  else if (search.value) search.value = '';

  if (!quiet) view.innerHTML = '<p class="dim">Loading...</p>';
  try {
    const out = await routes[key](arg);
    if (token !== state.nav) return; // a newer navigation started; drop this result
    view.innerHTML = out.html;
    if (out.after) out.after();
  } catch (err) {
    if (token !== state.nav) return;
    if (err instanceof AuthError) return showLogin();
    view.innerHTML = `<p class="error">Error: ${esc(err.message)}</p>`;
  }
}

/* ---------- login ---------- */

function renderHeader() {
  const u = state.user;
  $('#whoami').textContent = u ? `${u.username}${u.role === 'admin' ? ' (admin)' : ''}` : '';
  $('#b-account').hidden = !u;
  $('#logout').hidden = !u;
  $('#nav-admin').hidden = !(u && u.role === 'admin');
}

async function refreshAuth() {
  const s = await API.authStatus();
  state.user = s.user;
  renderHeader();
  return s;
}

function showLogin() {
  state.nav++; // cancel any pending render
  state.user = null;
  renderHeader();
  view.innerHTML = `<div class="login">
    <h1>Login</h1>
    <label class="field"><span>Username</span><input id="lg-user" autocomplete="username" autocapitalize="none" spellcheck="false"></label>
    <label class="field"><span>Password</span><input type="password" id="pw" autocomplete="current-password"></label>
    <button data-action="login">Enter</button>
    <p id="login-msg" class="error" style="margin-top:10px"></p>
  </div>`;
  $('#lg-user').focus();
}

/* ---------- modals ---------- */

function openModal(html) {
  modal.innerHTML = html;
  if (!modal.open) modal.showModal();
}
function closeModal() {
  if (modal.open) modal.close();
}

/* ---------- uploads and scans ---------- */

async function uploadFiles(files) {
  const out = $('#upload-out');
  out.hidden = false;
  const val = (id) => $(id).value.trim();
  const meta = { title: val('#m-title'), artist: val('#m-artist'), album: val('#m-album'), genre: val('#m-genre') };
  let added = 0;
  const failed = [];

  for (let i = 0; i < files.length; i++) {
    out.textContent = `Uploading ${i + 1}/${files.length}: ${files[i].name}`;
    const fd = new FormData();
    fd.append('file', files[i]);
    if (files.length === 1) Object.entries(meta).forEach(([k, v]) => { if (v) fd.append(k, v); });
    try {
      await API.uploadSong(fd);
      added++;
    } catch (err) {
      if (err instanceof AuthError) return showLogin();
      failed.push(`${files[i].name}: ${err.message}`);
    }
  }

  out.innerHTML = `Added ${added} of ${files.length}. <a href="#/songs">View songs</a>` +
    failed.map((f) => `<div class="error">${esc(f)}</div>`).join('');
}

/* ---------- click actions ---------- */

const listSong = (el) => state.lists[el.dataset.list]?.[Number(el.dataset.i)];

const actions = {
  play(el) {
    const list = state.lists[el.dataset.list];
    const song = listSong(el);
    if (song) player.playTrack(song, list);
  },

  'play-all'(el) {
    const list = state.lists[el.dataset.list];
    if (list?.length) player.playTrack(list[0], list);
  },

  async fav(el) {
    const r = await API.toggleFavorite(el.dataset.id);
    el.textContent = r.is_favorite ? '[*]' : '[ ]';
    Object.values(state.lists).forEach((l) => l.forEach((s) => { if (s.id === el.dataset.id) s.is_favorite = r.is_favorite; }));
    if (state.route === 'liked') route(true);
  },

  async 'pl-add'(el) {
    const playlists = await API.getPlaylists();
    const id = esc(el.dataset.id);
    openModal(`<h2>Add to playlist</h2>
      ${playlists.length
        ? `<div class="pick-list">${playlists.map((p) =>
            `<button data-action="pl-pick" data-pl="${esc(p.id)}" data-id="${id}" data-name="${esc(p.name)}">${esc(p.name)} (${p.song_count})</button>`).join('')}</div>`
        : '<p class="dim">No playlists yet.</p>'}
      <div class="row"><input id="pl-new-name" placeholder="new playlist name">
        <button data-action="pl-create" data-id="${id}">Create and add</button></div>
      <div class="row"><button data-action="close-modal">Cancel</button></div>`);
  },

  async 'pl-pick'(el) {
    await API.addSongToPlaylist(el.dataset.pl, el.dataset.id);
    closeModal();
    setStatus(`Added to "${el.dataset.name}"`);
  },

  async 'pl-create'(el) {
    const name = $('#pl-new-name').value.trim();
    if (!name) return;
    const pl = await API.createPlaylist(name);
    await API.addSongToPlaylist(pl.id, el.dataset.id);
    closeModal();
    setStatus(`Created "${name}" and added the song`);
  },

  async 'pl-new'() {
    const name = (prompt('Playlist name:') || '').trim();
    if (!name) return;
    await API.createPlaylist(name);
    route(true);
  },

  async 'pl-delete'(el) {
    if (!confirm('Delete this playlist? Your songs are not deleted.')) return;
    await API.deletePlaylist(el.dataset.pl);
    location.hash = '#/playlists';
  },

  async 'pl-remove'(el) {
    await API.removeSongFromPlaylist(el.dataset.pl, el.dataset.id);
    route(true);
  },

  async edit(el) {
    const s = await API.getSong(el.dataset.id);
    const field = (id, label, value) =>
      `<label class="field"><span>${label}</span><input id="${id}" value="${esc(value)}"></label>`;
    openModal(`<h2>Edit details</h2>
      ${field('e-title', 'Title', s.title)}
      ${field('e-artist', 'Artist', s.artist_name)}
      ${field('e-album', 'Album', s.album_title)}
      ${field('e-genre', 'Genre', s.genre)}
      <div class="row">
        <button data-action="edit-save" data-id="${esc(s.id)}">Save</button>
        <button data-action="close-modal">Cancel</button>
      </div>`);
  },

  async 'edit-save'(el) {
    const v = (id) => $(id).value.trim();
    const updated = await API.updateSong(el.dataset.id, {
      title: v('#e-title'), artist_name: v('#e-artist'), album_title: v('#e-album'), genre: v('#e-genre'),
    });
    closeModal();
    if (player.currentTrack?.id === updated.id) {
      Object.assign(player.currentTrack, updated);
      player.notifyState();
    }
    route(true);
  },

  async delete(el) {
    const row = el.closest('tr');
    const title = row?.querySelector('.t')?.firstChild?.textContent || 'this song';
    if (!confirm(`Remove "${title}" from the shared library?\n\nIt disappears for everyone, including from their playlists. Files stored by this app are deleted; files in folders added by scanning are never touched.`)) return;
    const r = await API.deleteSong(el.dataset.id);
    setStatus(r.file_deleted ? 'Song and its file deleted' : 'Removed from library; your original file was kept');
    route(true);
  },

  async scan(el) {
    const out = $('#scan-out');
    el.disabled = true;
    out.className = 'dim';
    out.textContent = 'Scanning...';
    try {
      const r = await API.triggerScan($('#scan-path').value.trim() || null, false);
      out.className = '';
      out.textContent = `Scanned ${r.scanned}, added ${r.added}, already indexed ${r.skipped}.`;
    } catch (err) {
      if (err instanceof AuthError) throw err;
      out.className = 'error';
      out.textContent = err.message;
    } finally {
      el.disabled = false;
    }
  },

  async login() {
    const msg = $('#login-msg');
    try {
      await API.login($('#lg-user').value, $('#pw').value);
      await refreshAuth();
      // a fresh login always starts at Home (never on a page left over from someone else)
      if (location.hash === '#/home') route(); else location.hash = '#/home';
    } catch (err) {
      msg.textContent = err instanceof AuthError ? 'Wrong username or password.' : err.message;
    }
  },

  async logout() {
    await API.logout();
    player.stop();
    showLogin();
  },

  account() {
    const u = state.user;
    openModal(`<h2>Account</h2>
      <p class="dim">Signed in as ${esc(u.username)} (${u.role === 'admin' ? 'admin' : 'friend'})</p>
      <label class="field"><span>Current password</span><input type="password" id="pw-cur" autocomplete="current-password"></label>
      <label class="field"><span>New password (10+ characters)</span><input type="password" id="pw-new" autocomplete="new-password"></label>
      <label class="field"><span>New password again</span><input type="password" id="pw-new2" autocomplete="new-password"></label>
      <div class="row">
        <button data-action="pw-save">Change password</button>
        <button data-action="close-modal">Close</button>
      </div>
      <p id="pw-msg" class="error" style="margin-top:10px"></p>`);
  },

  async 'pw-save'() {
    const msg = $('#pw-msg');
    if ($('#pw-new').value !== $('#pw-new2').value) { msg.textContent = 'The two new passwords do not match.'; return; }
    try {
      await API.changePassword($('#pw-cur').value, $('#pw-new').value);
      closeModal();
      setStatus('Password changed. Other devices were signed out.');
    } catch (err) {
      if (err instanceof AuthError) throw err;
      msg.textContent = err.message;
    }
  },

  async 'user-create'() {
    const msg = $('#nu-msg');
    const name = $('#nu-name').value.trim();
    try {
      await API.adminCreateUser(name, $('#nu-pw').value, $('#nu-role').value);
      setStatus(`Created "${name.toLowerCase()}". Send them the username and password.`);
      route(true);
    } catch (err) {
      if (err instanceof AuthError) throw err;
      msg.textContent = err.message;
    }
  },

  'user-pw'(el) {
    openModal(`<h2>Reset password</h2>
      <p class="dim">New password for ${esc(el.dataset.name)}. They are signed out everywhere and must use it next time.</p>
      <label class="field"><span>New password (10+ characters)</span><input id="rp-pw" autocomplete="off"></label>
      <div class="row">
        <button data-action="user-pw-save" data-id="${esc(el.dataset.id)}">Save</button>
        <button data-action="close-modal">Cancel</button>
      </div>
      <p id="rp-msg" class="error" style="margin-top:10px"></p>`);
  },

  async 'user-pw-save'(el) {
    try {
      await API.adminUpdateUser(el.dataset.id, { password: $('#rp-pw').value });
      closeModal();
      setStatus('Password reset. Send them the new one.');
    } catch (err) {
      if (err instanceof AuthError) throw err;
      $('#rp-msg').textContent = err.message;
    }
  },

  async 'user-toggle'(el) {
    await API.adminUpdateUser(el.dataset.id, { is_active: el.dataset.active !== 'true' });
    route(true);
  },

  'close-modal': closeModal,
};

document.addEventListener('click', async (e) => {
  const el = e.target.closest('[data-action]');
  if (!el || !actions[el.dataset.action]) return;
  try {
    await actions[el.dataset.action](el);
  } catch (err) {
    if (err instanceof AuthError) showLogin(); else setStatus(err.message, true);
  }
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.target.id === 'pw' || e.target.id === 'lg-user')) actions.login();
});

/* ---------- player deck ---------- */

function setupDeck() {
  const seek = $('#seek');
  const vol = $('#vol');
  const art = $('#art');
  const REP = { all: 'REP:ALL', one: 'REP:ONE', off: 'REP:OFF' };

  $('#b-play').addEventListener('click', () => player.togglePlayPause());
  $('#b-prev').addEventListener('click', () => player.prev());
  $('#b-next').addEventListener('click', () => player.next());
  $('#b-shuf').addEventListener('click', () => player.toggleShuffle());
  $('#b-rep').addEventListener('click', () => player.toggleRepeat());

  seek.addEventListener('input', () => { state.seeking = true; $('#t-cur').textContent = fmt(Number(seek.value)); });
  seek.addEventListener('change', () => { player.seek(Number(seek.value)); state.seeking = false; });

  try { vol.value = localStorage.getItem('adfree_vol') ?? vol.value; } catch { /* storage blocked */ }
  player.setVolume(Number(vol.value)); // the slider and the audio element start in agreement
  vol.addEventListener('input', () => {
    player.setVolume(Number(vol.value));
    try { localStorage.setItem('adfree_vol', vol.value); } catch { /* storage blocked */ }
  });

  player.subscribe((type, d) => {
    if (type === 'state') {
      $('#b-play').textContent = d.isPlaying ? 'PAUSE' : 'PLAY';
      $('#b-shuf').textContent = d.isShuffle ? 'SHUF:ON' : 'SHUF:OFF';
      $('#b-shuf').classList.toggle('on', d.isShuffle);
      $('#b-rep').textContent = REP[d.repeatMode];
      $('#b-rep').classList.toggle('on', d.repeatMode !== 'off');

      const t = d.track;
      $('#np-title').textContent = t ? t.title : '-- nothing loaded --';
      $('#np-sub').textContent = t ? `${t.artist_name || 'Unknown Artist'} / ${t.album_title || 'Unknown Album'}` : '\u00a0';
      art.innerHTML = t && t.artwork_url ? `<img src="${esc(t.artwork_url)}" alt="">` : 'NO ART';
      document.title = t ? `${t.title} - ${t.artist_name || 'Unknown Artist'}` : 'AdFreeShono';

      document.querySelectorAll('tr[data-id]').forEach((row) =>
        row.classList.toggle('playing', !!t && row.dataset.id === t.id));
    } else if (type === 'progress' && !state.seeking) {
      seek.max = d.duration || 100;
      seek.value = d.currentTime || 0;
      $('#t-cur').textContent = fmt(d.currentTime);
      $('#t-dur').textContent = fmt(d.duration);
    } else if (type === 'error') {
      setStatus(`Cannot play "${d.track.title}" (file missing?)`, true);
    }
  });

  player.notifyState(); // draw the initial labels
}

/* ---------- start ---------- */

function setupSearch() {
  const input = $('#search');
  let timer;
  input.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      const q = input.value.trim();
      if (q) location.hash = '#/search/' + encodeURIComponent(q);
      else if (state.route === 'search') location.hash = '#/home';
    }, 300);
  });
}

document.addEventListener('DOMContentLoaded', async () => {
  setupDeck();
  setupSearch();
  window.addEventListener('hashchange', () => route());

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => { /* optional */ });
  }

  try { await refreshAuth(); } catch { /* the first real request will surface any problem */ }
  if (!state.user) { showLogin(); return; }
  if (location.hash) route(); else location.hash = '#/home';
});
