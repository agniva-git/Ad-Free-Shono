import { API } from './api.js';

class AudioPlayer {
  constructor() {
    this.audio = new Audio();
    this.queue = [];
    this.queueIndex = -1;
    this.isShuffle = false;
    this.repeatMode = 'all'; // 'off' | 'all' | 'one'
    this.currentTrack = null;
    this.isPlaying = false;
    this.errorStreak = 0;
    this.listeners = new Set();

    this.initAudioEvents();
    this.initMediaSession();
  }

  initAudioEvents() {
    const a = this.audio;
    a.addEventListener('play', () => { this.isPlaying = true; this.notifyState(); });
    a.addEventListener('pause', () => { this.isPlaying = false; this.notifyState(); });
    a.addEventListener('playing', () => { this.errorStreak = 0; });
    a.addEventListener('timeupdate', () => this.notifyProgress());

    a.addEventListener('ended', () => {
      if (this.repeatMode === 'one') {
        a.currentTime = 0;
        a.play();
      } else {
        this.next();
      }
    });

    a.addEventListener('error', () => {
      if (!this.currentTrack) return;
      this.isPlaying = false;
      this.emit('error', { track: this.currentTrack });
      this.notifyState();
      // Skip a missing/unplayable file, but never loop forever if every file fails
      if (this.queue.length > 1 && this.errorStreak < this.queue.length) {
        this.errorStreak++;
        this.next();
      }
    });
  }

  initMediaSession() {
    if (!('mediaSession' in navigator)) return;
    const ms = navigator.mediaSession;
    ms.setActionHandler('play', () => this.togglePlayPause());
    ms.setActionHandler('pause', () => this.togglePlayPause());
    ms.setActionHandler('previoustrack', () => this.prev());
    ms.setActionHandler('nexttrack', () => this.next());
    ms.setActionHandler('seekto', (d) => { if (d.seekTime !== undefined) this.seek(d.seekTime); });
  }

  updateMediaSessionMetadata() {
    if (!('mediaSession' in navigator) || !this.currentTrack) return;
    const t = this.currentTrack;
    const artwork = t.artwork_url
      ? [{
          src: new URL(t.artwork_url, window.location.origin).href,
          sizes: '512x512',
          type: /\.png$/i.test(t.artwork_url) ? 'image/png' : 'image/jpeg',
        }]
      : [];
    navigator.mediaSession.metadata = new MediaMetadata({
      title: t.title,
      artist: t.artist_name || 'Unknown Artist',
      album: t.album_title || 'Unknown Album',
      artwork,
    });
  }

  subscribe(callback) {
    this.listeners.add(callback);
    return () => this.listeners.delete(callback);
  }

  emit(type, data) {
    this.listeners.forEach((cb) => cb(type, data));
  }

  notifyState() {
    this.emit('state', {
      isPlaying: this.isPlaying,
      track: this.currentTrack,
      isShuffle: this.isShuffle,
      repeatMode: this.repeatMode,
      queueIndex: this.queueIndex,
      queueLength: this.queue.length,
    });
  }

  notifyProgress() {
    const duration = this.audio.duration || this.currentTrack?.duration_seconds || 0;
    this.emit('progress', { currentTime: this.audio.currentTime, duration });

    // Lets the lock screen show a working scrubber
    const ms = 'mediaSession' in navigator ? navigator.mediaSession : null;
    if (ms && ms.setPositionState && Number.isFinite(duration) && duration > 0) {
      try {
        ms.setPositionState({
          duration,
          playbackRate: this.audio.playbackRate || 1,
          position: Math.min(this.audio.currentTime, duration),
        });
      } catch { /* some browsers reject odd values; not important */ }
    }
  }

  playTrack(track, queueList = null) {
    if (queueList) {
      this.queue = [...queueList];
      this.queueIndex = this.queue.findIndex((t) => t.id === track.id);
      if (this.queueIndex === -1) {
        this.queue.unshift(track);
        this.queueIndex = 0;
      }
    } else if (this.queue.length === 0) {
      this.queue = [track];
      this.queueIndex = 0;
    }

    this.currentTrack = track;
    this.audio.src = API.getStreamUrl(track.id);
    this.updateMediaSessionMetadata();

    const started = this.audio.play();
    if (started && started.then) {
      started.then(() => API.recordHistory(track.id))
             .catch((e) => console.warn('Playback did not start', e));
    }
    this.notifyState();
  }

  stop() {
    this.audio.pause();
    this.audio.removeAttribute('src');
    this.audio.load();
    this.currentTrack = null;
    this.queue = [];
    this.queueIndex = -1;
    this.isPlaying = false;
    this.notifyState();
    this.emit('progress', { currentTime: 0, duration: 0 });
  }

  togglePlayPause() {
    if (!this.currentTrack && this.queue.length > 0) {
      this.playTrack(this.queue[0]);
      return;
    }
    if (!this.currentTrack) return;
    if (this.audio.paused) this.audio.play(); else this.audio.pause();
  }

  next() {
    if (this.queue.length === 0) return;

    if (this.isShuffle && this.queue.length > 1) {
      let i;
      do { i = Math.floor(Math.random() * this.queue.length); } while (i === this.queueIndex);
      this.queueIndex = i;
    } else {
      this.queueIndex++;
      if (this.queueIndex >= this.queue.length) {
        if (this.repeatMode === 'all') {
          this.queueIndex = 0;
        } else {
          this.queueIndex = this.queue.length - 1;
          this.audio.pause();
          return;
        }
      }
    }
    this.playTrack(this.queue[this.queueIndex]);
  }

  prev() {
    if (this.queue.length === 0) return;
    if (this.audio.currentTime > 3) {
      this.audio.currentTime = 0;
      return;
    }
    this.queueIndex--;
    if (this.queueIndex < 0) this.queueIndex = this.repeatMode === 'all' ? this.queue.length - 1 : 0;
    this.playTrack(this.queue[this.queueIndex]);
  }

  seek(seconds) {
    if (this.audio.duration) {
      this.audio.currentTime = Math.min(Math.max(0, seconds), this.audio.duration);
    }
  }

  setVolume(fraction) {
    this.audio.volume = Math.min(Math.max(0, fraction), 1);
  }

  toggleShuffle() {
    this.isShuffle = !this.isShuffle;
    this.notifyState();
  }

  toggleRepeat() {
    this.repeatMode = { all: 'one', one: 'off', off: 'all' }[this.repeatMode];
    this.notifyState();
  }
}

export const player = new AudioPlayer();
