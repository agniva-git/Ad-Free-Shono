import { API } from './api.js';

class AudioPlayer {
  constructor() {
    this.audio = new Audio();
    this.queue = [];
    this.queueIndex = -1;
    this.isShuffle = false;
    this.repeatMode = 'all'; // 'off', 'all', 'one'
    this.currentTrack = null;
    this.isPlaying = false;
    this.listeners = new Set();

    this.initAudioEvents();
    this.initMediaSession();
  }

  initAudioEvents() {
    this.audio.addEventListener('play', () => {
      this.isPlaying = true;
      this.notifyState();
    });

    this.audio.addEventListener('pause', () => {
      this.isPlaying = false;
      this.notifyState();
    });

    this.audio.addEventListener('timeupdate', () => {
      this.notifyProgress();
    });

    this.audio.addEventListener('ended', () => {
      if (this.repeatMode === 'one') {
        this.audio.currentTime = 0;
        this.audio.play();
      } else {
        this.next();
      }
    });

    this.audio.addEventListener('error', (e) => {
      console.error('Audio playback error', e);
      this.isPlaying = false;
      this.notifyState();
    });
  }

  initMediaSession() {
    if ('mediaSession' in navigator) {
      navigator.mediaSession.setActionHandler('play', () => this.togglePlayPause());
      navigator.mediaSession.setActionHandler('pause', () => this.togglePlayPause());
      navigator.mediaSession.setActionHandler('previoustrack', () => this.prev());
      navigator.mediaSession.setActionHandler('nexttrack', () => this.next());
      navigator.mediaSession.setActionHandler('seekto', (details) => {
        if (details.seekTime !== undefined) {
          this.seek(details.seekTime);
        }
      });
    }
  }

  updateMediaSessionMetadata() {
    if ('mediaSession' in navigator && this.currentTrack) {
      const artwork = [];
      if (this.currentTrack.artwork_url) {
        artwork.push({
          src: window.location.origin + this.currentTrack.artwork_url,
          sizes: '512x512',
          type: 'image/jpeg'
        });
      }

      navigator.mediaSession.metadata = new MediaMetadata({
        title: this.currentTrack.title,
        artist: this.currentTrack.artist_name || 'Unknown Artist',
        album: this.currentTrack.album_title || 'Unknown Album',
        artwork: artwork
      });
    }
  }

  subscribe(callback) {
    this.listeners.add(callback);
    return () => this.listeners.delete(callback);
  }

  notifyState() {
    this.listeners.forEach(cb => cb('state', {
      isPlaying: this.isPlaying,
      track: this.currentTrack,
      isShuffle: this.isShuffle,
      repeatMode: this.repeatMode,
      queueIndex: this.queueIndex,
      queueLength: this.queue.length
    }));
  }

  notifyProgress() {
    this.listeners.forEach(cb => cb('progress', {
      currentTime: this.audio.currentTime,
      duration: this.audio.duration || this.currentTrack?.duration_seconds || 0
    }));
  }

  playTrack(track, queueList = null) {
    if (queueList) {
      this.queue = [...queueList];
      this.queueIndex = this.queue.findIndex(t => t.id === track.id);
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
    this.audio.play().then(() => {
      this.updateMediaSessionMetadata();
      API.recordHistory(track.id);
    }).catch(e => console.warn('Autoplay prevented or interrupted', e));

    this.notifyState();
  }

  togglePlayPause() {
    if (!this.currentTrack && this.queue.length > 0) {
      this.playTrack(this.queue[0]);
      return;
    }
    if (!this.currentTrack) return;

    if (this.audio.paused) {
      this.audio.play();
    } else {
      this.audio.pause();
    }
  }

  next() {
    if (this.queue.length === 0) return;

    if (this.isShuffle) {
      this.queueIndex = Math.floor(Math.random() * this.queue.length);
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
    if (this.queueIndex < 0) {
      this.queueIndex = this.repeatMode === 'all' ? this.queue.length - 1 : 0;
    }

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
    if (this.repeatMode === 'all') this.repeatMode = 'one';
    else if (this.repeatMode === 'one') this.repeatMode = 'off';
    else this.repeatMode = 'all';
    this.notifyState();
  }
}

export const player = new AudioPlayer();
