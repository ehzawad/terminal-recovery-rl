## Task: HLS Video Streaming Server

Build an HTTP Live Streaming (HLS) server that transcodes video into multiple bitrates and serves content through Nginx with a Node.js management backend.

## Technical Requirements

- **Language**: Node.js (v14+), Bash scripting
- **Dependencies**: FFmpeg, Nginx, hls.js
- **Input**: Video file at `/app/input.mp4`
- **Output**:
  - HLS segments and playlists in `/app/hls/` directory
  - Nginx configuration at `/app/nginx.conf`
  - Node.js server script at `/app/server.js`
  - HTML player at `/app/player.html`

## Implementation Requirements

### 1. Video Transcoding
Create a transcoding script that processes `/app/input.mp4` into three quality variants:
- **360p**: 640x360 resolution, 800k video bitrate, 128k audio bitrate
- **720p**: 1280x720 resolution, 2500k video bitrate, 128k audio bitrate
- **1080p**: 1920x1080 resolution, 5000k video bitrate, 192k audio bitrate

Each variant must generate:
- Segmented `.ts` files (6-second segments)
- Individual `.m3u8` playlist file

### 2. Master Playlist
Generate `/app/hls/master.m3u8` that references all three quality variants with proper bandwidth and resolution attributes.

### 3. Nginx Configuration
Create `/app/nginx.conf` with:
- Server listening on port 8080
- Root directory pointing to `/app`
- Proper MIME types for `.m3u8` (application/vnd.apple.mpegurl) and `.ts` (video/mp2t)
- CORS headers: `Access-Control-Allow-Origin: *`
- Location block `/hls/` serving HLS content

### 4. Node.js Server
Implement `/app/server.js` with:
- Express server on port 3000
- POST endpoint `/upload` accepting video file uploads (multipart/form-data)
- Uploaded files saved to `/app/uploads/` directory
- Automatic transcoding trigger after upload
- GET endpoint `/status/:filename` returning transcoding status as JSON

### 5. HTML5 Player
Create `/app/player.html` with:
- Video player using hls.js library
- Load master playlist from `http://localhost:8080/hls/master.m3u8`
- Display current quality level
- Quality selector controls

## Output Format

The `/app/hls/` directory structure:
```
hls/
├── master.m3u8
├── 360p/
│   ├── playlist.m3u8
│   └── segment*.ts
├── 720p/
│   ├── playlist.m3u8
│   └── segment*.ts
└── 1080p/
    ├── playlist.m3u8
    └── segment*.ts
```

Master playlist format must include BANDWIDTH and RESOLUTION attributes for each variant.

## Validation

The system must:
- Successfully transcode `/app/input.mp4` into all three quality levels
- Generate valid HLS playlists readable by standard HLS players
- Serve content through Nginx with correct MIME types and CORS headers
- Accept video uploads via Node.js endpoint and trigger transcoding
- Play video in browser using the HTML5 player with quality switching capability
