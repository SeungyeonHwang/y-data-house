#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::command;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::io::{Write, BufRead, BufReader};
use std::env;
use std::collections::HashMap;
use tauri::{Emitter, Window, State, Manager};
use urlencoding::decode;
use regex::Regex;
use std::sync::{Arc, atomic::{AtomicBool, Ordering}};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

// HTTP 서버 관련 imports
use warp::Filter;
use tokio::sync::RwLock;
use std::net::SocketAddr;

#[derive(Debug)]
struct VideoMetadata {
    title: String,
    channel: String,
    upload_date: Option<String>,
    duration: Option<String>,
    duration_seconds: Option<u32>,
    view_count: Option<u32>,
    topic: Option<Vec<String>>,
    video_id: Option<String>,
    source_url: Option<String>,
    excerpt: Option<String>,
}

#[derive(Serialize, Deserialize)]
struct VideoInfo {
    video_path: String,
    captions_path: String,
    title: String,
    channel: String,
    upload_date: Option<String>,
    duration: Option<String>,
    duration_seconds: Option<u32>,
    view_count: Option<u32>,
    topic: Option<Vec<String>>,
    video_id: Option<String>,
    source_url: Option<String>,
    excerpt: Option<String>,
}

#[derive(Serialize, Deserialize)]
struct ChannelInfo {
    url: String,
    name: String,
    enabled: bool,
}

#[derive(Serialize, Deserialize, Clone)]
struct DownloadProgress {
    channel: String,
    status: String,
    progress: f32,
    current_video: String,
    total_videos: u32,
    completed_videos: u32,
    log_message: String,
}

#[derive(Serialize, Deserialize)]
struct AppStatus {
    total_videos: u32,
    total_channels: u32,
    vault_size_mb: f64,
    last_download: Option<String>,
    vector_db_status: String,
}

#[derive(Serialize, Deserialize)]
struct ChannelVideos {
    channel_name: String,
    videos: Vec<VideoInfo>,
}

#[derive(Serialize, Deserialize)]
struct RecentVideos {
    channels: Vec<ChannelVideos>,
}

// 다운로드 중단을 위한 상태 관리
#[derive(Default, Clone)]
struct DownloadState {
    is_cancelled: Arc<AtomicBool>,
    current_process: Arc<Mutex<Option<std::process::Child>>>,
}

// 비디오 변환을 위한 상태 관리
#[derive(Default, Clone)]
struct ConversionState {
    is_converting: Arc<AtomicBool>,
    current_process: Arc<Mutex<Option<std::process::Child>>>,
}

// 임베딩 생성을 위한 상태 관리
#[derive(Default, Clone)]
struct EmbeddingState {
    is_cancelled: Arc<AtomicBool>,
    current_process: Arc<Mutex<Option<std::process::Child>>>,
}

// Range 지원 HTTP 서버 상태 관리
#[derive(Default)]
struct VideoServerState {
    server_port: Arc<RwLock<Option<u16>>>,
    server_handle: Arc<RwLock<Option<tokio::task::JoinHandle<()>>>>,
}

// 서버 에러 타입 정의
#[derive(Debug)]
struct ServerError;

impl warp::reject::Reject for ServerError {}

#[derive(Serialize, Deserialize, Clone)]
struct AIProgressUpdate {
    step: String,
    message: String,
    progress: f32,
    details: Option<String>,
}

// 프로젝트 루트 경로 찾기
fn get_project_root() -> PathBuf {
    let current_dir = env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    
    // src-tauri 디렉토리에서 실행되는 경우 2단계 상위로 이동 (src-tauri -> app -> project_root)
    if current_dir.file_name().map(|n| n == "src-tauri").unwrap_or(false) {
        current_dir.parent().and_then(|p| p.parent()).unwrap_or(&current_dir).to_path_buf()
    }
    // app 디렉토리에서 실행되는 경우 상위로 이동
    else if current_dir.file_name().map(|n| n == "app").unwrap_or(false) {
        current_dir.parent().unwrap_or(&current_dir).to_path_buf()
    } 
    // 현재 경로에 app 디렉토리가 포함된 경우 프로젝트 루트 찾기
    else if current_dir.to_string_lossy().contains("/app/") {
        let path_str = current_dir.to_string_lossy();
        if let Some(app_pos) = path_str.find("/app/") {
            PathBuf::from(&path_str[..app_pos])
        } else {
            current_dir
        }
    } else {
        current_dir
    }
}

// 디버그 정보 조회
#[command]
fn get_project_root_path() -> Result<String, String> {
    let project_root = get_project_root();
    Ok(project_root.to_string_lossy().to_string())
}

#[command]
fn get_debug_info() -> Result<String, String> {
    let current_dir = env::current_dir().map_err(|e| e.to_string())?;
    let project_root = get_project_root();
    let vault_path = project_root.join("vault");
    let channels_path = project_root.join("channels.txt");
    
    let mut info = Vec::new();
    info.push(format!("Current Directory: {}", current_dir.display()));
    info.push(format!("Project Root: {}", project_root.display()));
    info.push(format!("Vault Path: {} (exists: {})", vault_path.display(), vault_path.exists()));
    info.push(format!("Channels Path: {} (exists: {})", channels_path.display(), channels_path.exists()));
    
    // vault 내용 확인
    if vault_path.exists() {
        let videos_path = vault_path.join("10_videos");
        info.push(format!("Videos Path: {} (exists: {})", videos_path.display(), videos_path.exists()));
        
        if videos_path.exists() {
            match fs::read_dir(&videos_path) {
                Ok(entries) => {
                    let count = entries.count();
                    info.push(format!("Videos Directory Entries: {}", count));
                },
                Err(e) => info.push(format!("Error reading videos directory: {}", e)),
            }
        }
    }
    
    Ok(info.join("\n"))
}

// 비디오 목록 조회
#[command]
fn list_videos() -> Result<Vec<VideoInfo>, String> {
    let project_root = get_project_root();
    let root = project_root.join("vault").join("10_videos");
    let mut videos = Vec::new();
    
    if !root.exists() {
        return Err(format!("비디오 디렉토리가 존재하지 않습니다: {}", root.display()));
    }
    
    collect_videos(&root, &mut videos)?;
    Ok(videos)
}

fn collect_videos(dir: &PathBuf, videos: &mut Vec<VideoInfo>) -> Result<(), String> {
    let entries = fs::read_dir(dir).map_err(|e| format!("디렉토리 읽기 실패 {}: {}", dir.display(), e))?;
    
    for entry in entries {
        let entry = entry.map_err(|e| e.to_string())?;
        let path = entry.path();
        
        if path.is_dir() {
            collect_videos(&path, videos)?;
        } else if path.file_name().map(|n| n == "video.mp4").unwrap_or(false) {
            let folder = path.parent().unwrap();
            let captions_md = folder.join("captions.md");
            let captions_txt = folder.join("captions.txt");
            
            // YAML frontmatter에서 메타데이터 읽기
            let metadata = if captions_md.exists() {
                parse_markdown_metadata(&captions_md)?
            } else {
                VideoMetadata {
                    title: extract_title_from_path(&path),
                    channel: extract_channel_from_path(&path),
                    upload_date: None,
                    duration: None,
                    duration_seconds: None,
                    view_count: None,
                    topic: None,
                    video_id: None,
                    source_url: None,
                    excerpt: None,
                }
            };
            
            // 프로젝트 루트 기준 상대 경로 생성 (asset protocol 호환)
            let project_root = get_project_root();
            
            // 비디오 파일 상대 경로
            let video_relative = if let Ok(relative) = path.strip_prefix(&project_root) {
                relative.to_string_lossy().to_string()
            } else {
                path.to_string_lossy().to_string()
            };
            
            // 캡션 파일 상대 경로
            let captions_file = if captions_txt.exists() { captions_txt } else { captions_md };
            let captions_relative = if let Ok(relative) = captions_file.strip_prefix(&project_root) {
                relative.to_string_lossy().to_string()
            } else {
                captions_file.to_string_lossy().to_string()
            };
            
            videos.push(VideoInfo {
                video_path: video_relative,
                captions_path: captions_relative,
                title: metadata.title,
                channel: metadata.channel,
                upload_date: metadata.upload_date,
                duration: metadata.duration,
                duration_seconds: metadata.duration_seconds,
                view_count: metadata.view_count,
                topic: metadata.topic,
                video_id: metadata.video_id,
                source_url: metadata.source_url,
                excerpt: metadata.excerpt,
            });
        }
    }
    Ok(())
}

fn parse_markdown_metadata(path: &PathBuf) -> Result<VideoMetadata, String> {
    let content = fs::read_to_string(path).map_err(|e| e.to_string())?;
    
    if content.starts_with("---") {
        if let Some(end) = content[3..].find("---") {
            let yaml_content = &content[3..end+3];
            
            // YAML 필드 파싱
            let title = extract_yaml_field(yaml_content, "title").unwrap_or_else(|| "Unknown Title".to_string());
            let channel = extract_yaml_field(yaml_content, "channel").unwrap_or_else(|| "Unknown Channel".to_string());
            let upload_date = extract_yaml_field(yaml_content, "upload");
            let duration = extract_yaml_field(yaml_content, "duration");
            let duration_seconds = extract_yaml_field(yaml_content, "duration_seconds")
                .and_then(|s| s.parse::<u32>().ok());
            let view_count = extract_yaml_field(yaml_content, "view_count")
                .and_then(|s| s.parse::<u32>().ok());
            let video_id = extract_yaml_field(yaml_content, "video_id");
            let source_url = extract_yaml_field(yaml_content, "source_url");
            let excerpt = extract_yaml_field(yaml_content, "excerpt");
            
            // topic 배열 파싱
            let topic = extract_yaml_array(yaml_content, "topic");
            
            return Ok(VideoMetadata {
                title,
                channel,
                upload_date,
                duration,
                duration_seconds,
                view_count,
                topic,
                video_id,
                source_url,
                excerpt,
            });
        }
    }
    
    Ok(VideoMetadata {
        title: extract_title_from_path(&path.parent().unwrap().to_path_buf()),
        channel: extract_channel_from_path(&path.parent().unwrap().to_path_buf()),
        upload_date: None,
        duration: None,
        duration_seconds: None,
        view_count: None,
        topic: None,
        video_id: None,
        source_url: None,
        excerpt: None,
    })
}

fn extract_yaml_field(yaml: &str, field: &str) -> Option<String> {
    for line in yaml.lines() {
        if let Some(colon_pos) = line.find(':') {
            let key = line[..colon_pos].trim();
            if key == field {
                let value = line[colon_pos+1..].trim();
                // 따옴표 제거
                let cleaned = value.trim_matches('"').trim_matches('\'');
                return Some(cleaned.to_string());
            }
        }
    }
    None
}

fn extract_yaml_array(yaml: &str, field: &str) -> Option<Vec<String>> {
    for line in yaml.lines() {
        if let Some(colon_pos) = line.find(':') {
            let key = line[..colon_pos].trim();
            if key == field {
                let value = line[colon_pos+1..].trim();
                
                // 배열 형태 파싱: ['item1', 'item2'] 또는 [item1, item2]
                if value.starts_with('[') && value.ends_with(']') {
                    let inner = &value[1..value.len()-1];
                    let items: Vec<String> = inner
                        .split(',')
                        .map(|s| s.trim().trim_matches('"').trim_matches('\'').to_string())
                        .filter(|s| !s.is_empty())
                        .collect();
                    return if items.is_empty() { None } else { Some(items) };
                }
            }
        }
    }
    None
}

fn extract_title_from_path(path: &PathBuf) -> String {
    path.file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_else(|| "Unknown Title".to_string())
}

fn extract_channel_from_path(path: &PathBuf) -> String {
    let parts: Vec<_> = path.components().collect();
    for (i, component) in parts.iter().enumerate() {
        if component.as_os_str() == "10_videos" && i + 1 < parts.len() {
            let raw_name = parts[i + 1].as_os_str().to_string_lossy();
            // URL 디코딩 시도
            match decode(&raw_name) {
                Ok(decoded) => return decoded.to_string(),
                Err(_) => return raw_name.to_string(), // 디코딩 실패시 원본 반환
            }
        }
    }
    "Unknown Channel".to_string()
}

// 채널 목록 관리
#[command]
fn list_channels() -> Result<Vec<ChannelInfo>, String> {
    let project_root = get_project_root();
    let channels_file = project_root.join("channels.txt");
    
    if !channels_file.exists() {
        return Ok(vec![]);
    }
    
    let content = fs::read_to_string(&channels_file).map_err(|e| e.to_string())?;
    let mut channels = Vec::new();
    
    for line in content.lines() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        
        let enabled = !line.starts_with("# ");
        let url = if enabled { line } else { &line[2..] };
        let name = extract_channel_name_from_url(url);
        
        channels.push(ChannelInfo {
            url: url.to_string(),
            name,
            enabled,
        });
    }
    
    Ok(channels)
}

fn extract_channel_name_from_url(url: &str) -> String {
    let raw_name = if let Some(at_pos) = url.rfind('@') {
        &url[at_pos+1..]
    } else if let Some(slash_pos) = url.rfind('/') {
        &url[slash_pos+1..]
    } else {
        url
    };
    
    // URL 디코딩 시도
    match decode(raw_name) {
        Ok(decoded) => decoded.to_string(),
        Err(_) => raw_name.to_string(), // 디코딩 실패시 원본 반환
    }
}

#[command]
fn add_channel(url: String) -> Result<(), String> {
    let project_root = get_project_root();
    let channels_file = project_root.join("channels.txt");
    
    // channels.txt가 없으면 생성
    if !channels_file.exists() {
        create_channels_file()?;
    }
    
    // 중복 체크
    let existing_channels = list_channels()?;
    if existing_channels.iter().any(|c| c.url == url) {
        return Err("채널이 이미 존재합니다".to_string());
    }
    
    // 채널 추가
    let mut file = fs::OpenOptions::new()
        .append(true)
        .open(&channels_file)
        .map_err(|e| e.to_string())?;
    
    writeln!(file, "{}", url).map_err(|e| e.to_string())?;
    
    Ok(())
}

#[command]
fn remove_channel(url: String) -> Result<(), String> {
    let project_root = get_project_root();
    let channels_file = project_root.join("channels.txt");
    
    if !channels_file.exists() {
        return Err("channels.txt 파일이 존재하지 않습니다".to_string());
    }
    
    let content = fs::read_to_string(&channels_file).map_err(|e| e.to_string())?;
    let new_content: Vec<String> = content
        .lines()
        .filter(|line| {
            let line = line.trim();
            if line.starts_with("# ") {
                &line[2..] != url
            } else {
                line != url
            }
        })
        .map(|s| s.to_string())
        .collect();
    
    fs::write(&channels_file, new_content.join("\n")).map_err(|e| e.to_string())?;
    
    Ok(())
}

#[command]
fn toggle_channel(url: String) -> Result<(), String> {
    let project_root = get_project_root();
    let channels_file = project_root.join("channels.txt");
    
    if !channels_file.exists() {
        return Err("channels.txt 파일이 존재하지 않습니다".to_string());
    }
    
    let content = fs::read_to_string(&channels_file).map_err(|e| e.to_string())?;
    let new_content: Vec<String> = content
        .lines()
        .map(|line| {
            let line = line.trim();
            if line == url {
                format!("# {}", line)
            } else if line.starts_with("# ") && &line[2..] == url {
                line[2..].to_string()
            } else {
                line.to_string()
            }
        })
        .collect();
    
    fs::write(&channels_file, new_content.join("\n")).map_err(|e| e.to_string())?;
    
    Ok(())
}

fn create_channels_file() -> Result<(), String> {
    let project_root = get_project_root();
    let channels_file = project_root.join("channels.txt");
    let content = r#"# Y-Data-House 채널 목록
# 한 줄에 하나씩 YouTube 채널 URL을 입력하세요
# '#'로 시작하는 줄은 주석으로 처리됩니다
#
# 예시:
# https://www.youtube.com/@리베라루츠대학
# https://www.youtube.com/@채널명2
#
# 아래에 다운로드할 채널 URL을 추가하세요:

"#;
    
    fs::write(&channels_file, content).map_err(|e| e.to_string())?;
    Ok(())
}

// 다운로드 중단 명령어
#[command]
async fn cancel_download(state: State<'_, DownloadState>) -> Result<(), String> {
    // 중단 플래그 설정
    state.is_cancelled.store(true, Ordering::SeqCst);
    
    // 현재 실행 중인 프로세스 강제 종료
    if let Ok(mut process_guard) = state.current_process.lock() {
        if let Some(mut child) = process_guard.take() {
            // 🔥 IMPROVED: 더 강력한 프로세스 종료
            #[cfg(unix)]
            {
                // SIGTERM 먼저 시도
                let _ = child.kill();
                
                // 1초 대기 후 강제 종료 확인
                thread::sleep(Duration::from_millis(1000));
                
                // 여전히 실행 중이면 SIGKILL 시도
                match child.try_wait() {
                    Ok(Some(_)) => {
                        // 프로세스가 종료됨
                    }
                    Ok(None) => {
                        // 여전히 실행 중, 강제 종료 시도
                        let pid = child.id();
                        let _ = Command::new("kill")
                            .args(&["-9", &pid.to_string()])
                            .output();
                        let _ = child.wait();
                    }
                    Err(_) => {
                        // 오류 발생, 그냥 대기
                        let _ = child.wait();
                    }
                }
            }
            
            #[cfg(windows)]
            {
                // Windows에서는 기본 kill 사용
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
    
    // 중단 시 정리 작업 수행
    cleanup_incomplete_downloads().await?;
    
    Ok(())
}

// 불완전한 다운로드 정리
async fn cleanup_incomplete_downloads() -> Result<(), String> {
    let project_root = get_project_root();
    let downloads_dir = project_root.join("vault").join("downloads");
    
    if !downloads_dir.exists() {
        return Ok(());
    }
    
    // downloads 폴더에서 불완전한 파일들 찾기
    let entries = fs::read_dir(&downloads_dir).map_err(|e| e.to_string())?;
    
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_file() {
            let filename = path.file_name().unwrap_or_default().to_string_lossy();
            
            // 임시 파일들 (.part, .ytdl, .tmp 등) 삭제
            if filename.ends_with(".part") || 
               filename.ends_with(".ytdl") || 
               filename.ends_with(".tmp") ||
               filename.contains(".f") && (filename.contains(".mp4") || filename.contains(".webm")) {
                if let Err(e) = fs::remove_file(&path) {
                    eprintln!("임시 파일 삭제 실패 {}: {}", path.display(), e);
                }
            }
        }
    }
    
    Ok(())
}

// yt-dlp 진행률 파싱 함수
fn parse_ytdlp_progress(line: &str, window: &Window, channel_name: &str) {
    // [download] 25.5% of 12.34MiB at 1.23MiB/s ETA 00:10
    if let Some(percent_start) = line.find("] ") {
        if let Some(percent_end) = line[percent_start + 2..].find("% of") {
            let percent_str = &line[percent_start + 2..percent_start + 2 + percent_end];
            if let Ok(percent) = percent_str.parse::<f32>() {
                let progress = DownloadProgress {
                    channel: channel_name.to_string(),
                    status: "다운로드 중".to_string(),
                    progress: percent,
                    current_video: format!("📥 진행률: {:.1}%", percent),
                    total_videos: 1,
                    completed_videos: 0,
                    log_message: line.to_string(),
                };
                let _ = window.emit("download-progress", &progress);
            }
        }
    }
}

// 실시간 출력 캡처를 위한 헬퍼 함수
fn run_process_with_realtime_output(
    mut child: std::process::Child,
    window: &Window,
    channel_name: &str,
    state: &State<'_, DownloadState>,
) -> Result<(u32, u32, std::process::ExitStatus), String> {
    let stdout = child.stdout.take().ok_or("stdout 캡처 실패")?;
    let stderr = child.stderr.take().ok_or("stderr 캡처 실패")?;
    
    let mut channel_total_videos = 0u32;
    let mut channel_downloaded_videos = 0u32;
    
    // 통계 정보 전송을 위한 채널
    let (channel_total_tx, channel_total_rx) = std::sync::mpsc::channel::<u32>();
    let (channel_downloaded_tx, channel_downloaded_rx) = std::sync::mpsc::channel::<u32>();
    
    // 🔥 NEW: 마지막 로그 수신 시간 추적 (15초 타임아웃으로 단축)
    let last_activity = Arc::new(Mutex::new(Instant::now()));
    let timeout_duration = Duration::from_secs(15);  // 15초로 단축
    
    // stdout 실시간 읽기 스레드
    let window_clone = window.clone();
    let channel_name_clone = channel_name.to_string();
    let is_cancelled = state.is_cancelled.clone();
    let last_activity_clone = last_activity.clone();
    
    let stdout_handle = thread::spawn(move || {
        let reader = BufReader::new(stdout);
        
        for line in reader.lines() {
            // 중단 신호 확인
            if is_cancelled.load(Ordering::SeqCst) {
                break;
            }
            
            match line {
                Ok(line_str) => {
                    if line_str.trim().is_empty() {
                        continue;
                    }
                    
                    // 🔥 NEW: 활동 시간 업데이트 (타임아웃 방지)
                    if let Ok(mut last_time) = last_activity_clone.lock() {
                        *last_time = Instant::now();
                    }
                    
                    // 실시간 로그 메시지 전송
                    let log_progress = DownloadProgress {
                        channel: channel_name_clone.clone(),
                        status: "진행 중".to_string(),
                        progress: 0.0,
                        current_video: format!("📺 {}", channel_name_clone),
                        total_videos: 0,
                        completed_videos: 0,
                        log_message: line_str.clone(),
                    };
                    let _ = window_clone.emit("download-progress", &log_progress);
                    
                    // 비디오 수 파싱
                    if line_str.contains("총") && line_str.contains("개 영상을 발견했습니다") {
                        if let Some(start) = line_str.find("총 ") {
                            if let Some(end) = line_str[start..].find("개 영상을 발견했습니다") {
                                let number_str = line_str[start + 2..start + end].trim();
                                if let Ok(count) = number_str.parse::<u32>() {
                                    let _ = channel_total_tx.send(count);
                                }
                            }
                        }
                    }
                    
                    // 다운로드 완료 수 파싱
                    if line_str.contains("다운로드 완료:") && line_str.contains("개 성공") {
                        if let Some(start) = line_str.find("다운로드 완료: ") {
                            if let Some(end) = line_str[start..].find("개 성공") {
                                let number_str = line_str[start + 7..start + end].trim();
                                if let Ok(count) = number_str.parse::<u32>() {
                                    let _ = channel_downloaded_tx.send(count);
                                }
                            }
                        }
                    }
                    
                    // yt-dlp 진행률 파싱
                    if line_str.contains("[download]") && line_str.contains("%") {
                        parse_ytdlp_progress(&line_str, &window_clone, &channel_name_clone);
                    }
                }
                Err(_) => break,
            }
        }
    });
    
    // stderr 실시간 읽기 스레드
    let window_clone = window.clone();
    let channel_name_clone = channel_name.to_string();
    let is_cancelled_stderr = state.is_cancelled.clone();
    let last_activity_stderr = last_activity.clone();
    
    let stderr_handle = thread::spawn(move || {
        let reader = BufReader::new(stderr);
        
        for line in reader.lines() {
            // 중단 신호 확인
            if is_cancelled_stderr.load(Ordering::SeqCst) {
                break;
            }
            
            match line {
                Ok(line_str) => {
                    if !line_str.trim().is_empty() {
                        // 🔥 NEW: 활동 시간 업데이트 (타임아웃 방지)
                        if let Ok(mut last_time) = last_activity_stderr.lock() {
                            *last_time = Instant::now();
                        }
                        
                        let stderr_progress = DownloadProgress {
                            channel: channel_name_clone.clone(),
                            status: "정보".to_string(),
                            progress: 0.0,
                            current_video: format!("📺 {}", channel_name_clone),
                            total_videos: 0,
                            completed_videos: 0,
                            log_message: format!("⚠️ {}", line_str),
                        };
                        let _ = window_clone.emit("download-progress", &stderr_progress);
                    }
                }
                Err(_) => break,
            }
        }
    });
    
    // 프로세스 완료 대기 (타임아웃은 위에서 이미 설정됨)
    let mut process_completed = false;
    while !process_completed {
        // 중단 신호 확인
        if state.is_cancelled.load(Ordering::SeqCst) {
            return Err("다운로드가 중단되었습니다".to_string());
        }
        
        // 🔥 NEW: 타임아웃 감지 및 자동 kill (30초로 단축)
        if let Ok(last_time) = last_activity.lock() {
            if last_time.elapsed() > timeout_duration {
                eprintln!("⚠️ 15초간 로그 없음 - 프로세스 강제 종료");
                let _ = child.kill();
                return Err("프로세스 타임아웃으로 중단되었습니다 (15초간 응답 없음)".to_string());
            }
        }
        
        // 프로세스 상태 확인
        match child.try_wait() {
            Ok(Some(_)) => {
                process_completed = true;
            }
            Ok(None) => {
                // 아직 실행 중, 잠시 대기
                thread::sleep(Duration::from_millis(100));
            }
            Err(_) => {
                process_completed = true;
            }
        }
    }
    
    // 스레드 완료 대기
    let _ = stdout_handle.join();
    let _ = stderr_handle.join();
    
    // 통계 정보 수집
    if let Ok(count) = channel_total_rx.try_recv() {
        channel_total_videos = count;
    }
    if let Ok(count) = channel_downloaded_rx.try_recv() {
        channel_downloaded_videos = count;
    }
    
    // 프로세스 최종 상태 확인
    let output = child.wait_with_output().map_err(|e| e.to_string())?;
    
    Ok((channel_total_videos, channel_downloaded_videos, output.status))
}

// 비디오 다운로드 (실시간 진행 상황 포함)
#[command]
async fn download_videos_with_progress(window: Window, state: State<'_, DownloadState>) -> Result<String, String> {
    let channels = list_channels()?;
    let enabled_channels: Vec<_> = channels.into_iter().filter(|c| c.enabled).collect();
    
    if enabled_channels.is_empty() {
        return Err("활성화된 채널이 없습니다".to_string());
    }
    
    // Python 가상환경 확인
    let project_root = get_project_root();
    let venv_python = project_root.join("venv").join("bin").join("python3");
    if !venv_python.exists() {
        return Err(format!("Python 가상환경이 설정되지 않았습니다: {}", venv_python.display()));
    }
    
    // 다운로드 시작 시 중단 플래그 초기화
    state.is_cancelled.store(false, Ordering::SeqCst);
    
    // 시작 메시지
    let start_progress = DownloadProgress {
        channel: "전체".to_string(),
        status: "시작".to_string(),
        progress: 0.0,
        current_video: "배치 다운로드 시작".to_string(),
        total_videos: 0,
        completed_videos: 0,
        log_message: "🚀 모든 활성화된 채널의 배치 다운로드를 시작합니다...".to_string(),
    };
    let _ = window.emit("download-progress", &start_progress);
    
    // 🔥 IMPROVED: batch 명령어 사용으로 모든 채널을 안정적으로 배치 처리 + 디버그 모드
    let child = Command::new(&venv_python)
        .args(&["-u", "-m", "ydh", "batch"])
        .current_dir(&project_root)
        .env("PYTHONUNBUFFERED", "1")        // Python 출력 버퍼링 방지
        .env("PYTHONIOENCODING", "utf-8")    // UTF-8 인코딩 강제
        .env("YDH_YTDLP_SLEEP_INTERVAL", "2")     // 요청 간 2초 지연
        .env("YDH_YTDLP_MAX_SLEEP_INTERVAL", "5") // 최대 5초 랜덤 지연
        .env("YDH_YTDLP_SLEEP_REQUESTS", "20")    // 20회마다 추가 슬립
        .env("YDH_YTDLP_SOCKET_TIMEOUT", "8")     // 8초 소켓 타임아웃
        .env("YDH_YTDLP_RETRIES", "1")            // 1회 재시도
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| e.to_string())?;
    
    // 현재 프로세스를 상태에 저장 (중단을 위해)
    {
        if let Ok(mut process_guard) = state.current_process.lock() {
            *process_guard = Some(child);
        }
    }
    
    // 프로세스를 다시 가져와서 처리
    let child = if let Ok(mut process_guard) = state.current_process.lock() {
        process_guard.take().unwrap()
    } else {
        return Err("프로세스 접근 실패".to_string());
    };
    
    // 🔥 NEW: 실시간 출력 캡처로 프로세스 실행
    match run_process_with_realtime_output(child, &window, "전체 채널", &state) {
        Ok((total, downloaded, status)) => {
            if status.success() {
                let success_progress = DownloadProgress {
                    channel: "전체".to_string(),
                    status: "완료".to_string(),
                    progress: 100.0,
                    current_video: "모든 채널".to_string(),
                    total_videos: total,
                    completed_videos: downloaded,
                    log_message: format!("🎉 배치 다운로드 완료! (총 {}/{}개)", downloaded, total),
                };
                let _ = window.emit("download-progress", &success_progress);
                return Ok(format!("✅ 배치 다운로드 성공: {}/{}개 영상 다운로드 완료", downloaded, total));
            } else {
                let error_progress = DownloadProgress {
                    channel: "전체".to_string(),
                    status: "실패".to_string(),
                    progress: 100.0,
                    current_video: "모든 채널".to_string(),
                    total_videos: total,
                    completed_videos: downloaded,
                    log_message: "❌ 배치 다운로드 중 오류 발생".to_string(),
                };
                let _ = window.emit("download-progress", &error_progress);
                return Err("배치 다운로드 중 오류가 발생했습니다".to_string());
            }
        }
        Err(err) => {
            if err.contains("중단") {
                return Ok("다운로드가 중단되었습니다".to_string());
            } else {
                return Err(format!("배치 다운로드 실패: {}", err));
            }
        }
    }
}

// 기존 다운로드 함수 (호환성 유지)
#[command]
async fn download_videos() -> Result<String, String> {
    // 단순히 배치 다운로드 함수 호출
    let project_root = get_project_root();
    let venv_python = project_root.join("venv").join("bin").join("python3");
    if !venv_python.exists() {
        return Err(format!("Python 가상환경이 설정되지 않았습니다: {}", venv_python.display()));
    }

    let output = Command::new(&venv_python)
        .args(&["-u", "-m", "ydh", "batch"])
        .current_dir(&project_root)
        .env("PYTHONUNBUFFERED", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .output()
        .map_err(|e| e.to_string())?;

    if output.status.success() {
        Ok("✅ 배치 다운로드 완료".to_string())
    } else {
        let error = String::from_utf8_lossy(&output.stderr);
        Err(format!("❌ 배치 다운로드 실패: {}", error))
    }
}

// 품질 매개변수를 받는 다운로드 함수 (batch 처리)
#[command]
async fn download_videos_with_progress_and_quality(window: Window, state: State<'_, DownloadState>, quality: String) -> Result<String, String> {
    let channels = list_channels()?;
    let enabled_channels: Vec<_> = channels.into_iter().filter(|c| c.enabled).collect();
    
    if enabled_channels.is_empty() {
        return Err("활성화된 채널이 없습니다".to_string());
    }
    
    // Python 가상환경 확인
    let project_root = get_project_root();
    let venv_python = project_root.join("venv").join("bin").join("python3");
    if !venv_python.exists() {
        return Err(format!("Python 가상환경이 설정되지 않았습니다: {}", venv_python.display()));
    }
    
    // 다운로드 시작 시 중단 플래그 초기화
    state.is_cancelled.store(false, Ordering::SeqCst);
    
    // 시작 메시지
    let start_progress = DownloadProgress {
        channel: "전체".to_string(),
        status: "시작".to_string(),
        progress: 0.0,
        current_video: format!("배치 다운로드 시작 (품질: {})", quality),
        total_videos: 0,
        completed_videos: 0,
        log_message: format!("🚀 모든 활성화된 채널의 배치 다운로드를 시작합니다... (품질: {})", quality),
    };
    let _ = window.emit("download-progress", &start_progress);
    
    // 🔥 IMPROVED: batch 명령어 사용으로 모든 채널을 안정적으로 배치 처리
    let child = Command::new(&venv_python)
        .args(&["-u", "-m", "ydh", "batch"])
        .current_dir(&project_root)
        .env("PYTHONUNBUFFERED", "1")        // Python 출력 버퍼링 방지
        .env("PYTHONIOENCODING", "utf-8")    // UTF-8 인코딩 강제
        .env("YDH_YTDLP_SLEEP_INTERVAL", "2")     // 요청 간 2초 지연
        .env("YDH_YTDLP_MAX_SLEEP_INTERVAL", "5") // 최대 5초 랜덤 지연
        .env("YDH_YTDLP_SLEEP_REQUESTS", "20")    // 20회마다 추가 슬립
        .env("YDH_YTDLP_SOCKET_TIMEOUT", "8")     // 8초 소켓 타임아웃
        .env("YDH_YTDLP_RETRIES", "1")            // 1회 재시도
        .env("YDH_VIDEO_QUALITY", &quality)  // 품질 설정
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| e.to_string())?;
    
    // 현재 프로세스를 상태에 저장 (중단을 위해)
    {
        if let Ok(mut process_guard) = state.current_process.lock() {
            *process_guard = Some(child);
        }
    }
    
    // 프로세스를 다시 가져와서 처리
    let child = if let Ok(mut process_guard) = state.current_process.lock() {
        process_guard.take().unwrap()
    } else {
        return Err("프로세스 접근 실패".to_string());
    };
    
    // 🔥 NEW: 실시간 출력 캡처로 프로세스 실행
    match run_process_with_realtime_output(child, &window, "전체 채널", &state) {
        Ok((total, downloaded, status)) => {
            if status.success() {
                let success_progress = DownloadProgress {
                    channel: "전체".to_string(),
                    status: "완료".to_string(),
                    progress: 100.0,
                    current_video: "모든 채널".to_string(),
                    total_videos: total,
                    completed_videos: downloaded,
                    log_message: format!("🎉 배치 다운로드 완료! (총 {}/{}개, 품질: {})", downloaded, total, quality),
                };
                let _ = window.emit("download-progress", &success_progress);
                Ok(format!("✅ 배치 다운로드 성공: {}/{}개 영상 다운로드 완료 (품질: {})", downloaded, total, quality))
            } else {
                let error_progress = DownloadProgress {
                    channel: "전체".to_string(),
                    status: "실패".to_string(),
                    progress: 100.0,
                    current_video: "모든 채널".to_string(),
                    total_videos: total,
                    completed_videos: downloaded,
                    log_message: "❌ 배치 다운로드 중 오류 발생".to_string(),
                };
                let _ = window.emit("download-progress", &error_progress);
                return Err("배치 다운로드 중 오류가 발생했습니다".to_string());
            }
        }
        Err(err) => {
            if err.contains("중단") {
                return Ok("다운로드가 중단되었습니다".to_string());
            } else {
                return Err(format!("배치 다운로드 실패: {}", err));
            }
        }
    }
}

// 🔍 전체 무결성 검사 다운로드 (--full-scan)
#[command]
async fn download_videos_full_scan_with_progress(window: Window, state: State<'_, DownloadState>) -> Result<String, String> {
    let channels = list_channels()?;
    let enabled_channels: Vec<_> = channels.into_iter().filter(|c| c.enabled).collect();
    
    if enabled_channels.is_empty() {
        return Err("활성화된 채널이 없습니다".to_string());
    }
    
    // Python 가상환경 확인
    let project_root = get_project_root();
    let venv_python = project_root.join("venv").join("bin").join("python3");
    if !venv_python.exists() {
        return Err(format!("Python 가상환경이 설정되지 않았습니다: {}", venv_python.display()));
    }
    
    // 다운로드 시작 시 중단 플래그 초기화
    state.is_cancelled.store(false, Ordering::SeqCst);
    
    // 시작 메시지
    let start_progress = DownloadProgress {
        channel: "전체".to_string(),
        status: "시작".to_string(),
        progress: 0.0,
        current_video: "전체 무결성 검사 시작".to_string(),
        total_videos: 0,
        completed_videos: 0,
        log_message: "🔍 전체 무결성 검사를 시작합니다. 모든 영상을 확인하여 누락된 영상을 복구합니다...".to_string(),
    };
    let _ = window.emit("download-progress", &start_progress);
    
    // 🔥 전체 무결성 검사 모드: --full-scan 플래그 사용
    let child = Command::new(&venv_python)
        .args(&["-u", "-m", "ydh", "batch", "--full-scan"])
        .current_dir(&project_root)
        .env("PYTHONUNBUFFERED", "1")        // Python 출력 버퍼링 방지
        .env("PYTHONIOENCODING", "utf-8")    // UTF-8 인코딩 강제
        .env("YDH_YTDLP_SLEEP_INTERVAL", "2")     // 요청 간 2초 지연
        .env("YDH_YTDLP_MAX_SLEEP_INTERVAL", "5") // 최대 5초 랜덤 지연
        .env("YDH_YTDLP_SLEEP_REQUESTS", "20")    // 20회마다 추가 슬립
        .env("YDH_YTDLP_SOCKET_TIMEOUT", "10")    // 전체 검사시 타임아웃 증가
        .env("YDH_YTDLP_RETRIES", "2")            // 전체 검사시 재시도 횟수 증가
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| e.to_string())?;
    
    // 현재 프로세스를 상태에 저장 (중단을 위해)
    {
        if let Ok(mut process_guard) = state.current_process.lock() {
            *process_guard = Some(child);
        }
    }
    
    // 프로세스를 다시 가져와서 처리
    let child = if let Ok(mut process_guard) = state.current_process.lock() {
        process_guard.take().unwrap()
    } else {
        return Err("프로세스 접근 실패".to_string());
    };
    
    // 🔥 실시간 출력 캡처로 프로세스 실행
    match run_process_with_realtime_output(child, &window, "전체 무결성 검사", &state) {
        Ok((total, downloaded, status)) => {
            if status.success() {
                let success_progress = DownloadProgress {
                    channel: "전체".to_string(),
                    status: "완료".to_string(),
                    progress: 100.0,
                    current_video: "모든 채널".to_string(),
                    total_videos: total,
                    completed_videos: downloaded,
                    log_message: format!("🎉 전체 무결성 검사 완료! 누락된 {}개 영상을 복구했습니다.", downloaded),
                };
                let _ = window.emit("download-progress", &success_progress);
                return Ok(format!("✅ 전체 무결성 검사 성공: {}개 누락 영상 복구 완료", downloaded));
            } else {
                let error_progress = DownloadProgress {
                    channel: "전체".to_string(),
                    status: "실패".to_string(),
                    progress: 100.0,
                    current_video: "모든 채널".to_string(),
                    total_videos: total,
                    completed_videos: downloaded,
                    log_message: "❌ 전체 무결성 검사 중 오류 발생".to_string(),
                };
                let _ = window.emit("download-progress", &error_progress);
                return Err("전체 무결성 검사 중 오류가 발생했습니다".to_string());
            }
        }
        Err(err) => {
            if err.contains("중단") {
                return Ok("전체 무결성 검사가 중단되었습니다".to_string());
            } else {
                return Err(format!("전체 무결성 검사 실패: {}", err));
            }
        }
    }
}

// 사용 가능한 채널 목록 조회
#[command]
fn get_available_channels_for_embedding() -> Result<Vec<String>, String> {
    let project_root = get_project_root();
    let videos_path = project_root.join("vault").join("10_videos");
    
    if !videos_path.exists() {
        return Ok(Vec::new());
    }
    
    let mut channels = Vec::new();
    
    match fs::read_dir(&videos_path) {
        Ok(entries) => {
            for entry in entries {
                if let Ok(entry) = entry {
                    let path = entry.path();
                    if path.is_dir() {
                        if let Some(channel_name) = path.file_name() {
                            if let Some(name_str) = channel_name.to_str() {
                                channels.push(name_str.to_string());
                            }
                        }
                    }
                }
            }
        }
        Err(e) => return Err(format!("채널 디렉토리 읽기 실패: {}", e)),
    }
    
    channels.sort();
    Ok(channels)
}

// 채널별 임베딩 생성 (진행 상황 포함)
#[command]
async fn create_embeddings_for_channels_with_progress(
    window: Window, 
    channels: Vec<String>,
    state: State<'_, EmbeddingState>
) -> Result<String, String> {
    let project_root = get_project_root();
    let embed_script = project_root.join("vault").join("90_indices").join("embed.py");
    if !embed_script.exists() {
        return Err(format!("embed.py 스크립트를 찾을 수 없습니다: {}", embed_script.display()));
    }
    
    let venv_python = project_root.join("venv").join("bin").join("python");
    if !venv_python.exists() {
        return Err(format!("Python 가상환경이 설정되지 않았습니다: {}", venv_python.display()));
    }
    
    // 중단 상태 초기화
    state.is_cancelled.store(false, Ordering::Relaxed);
    
    if channels.is_empty() {
        return Err("선택된 채널이 없습니다.".to_string());
    }
    
    let total_channels = channels.len() as u32;
    let mut all_output = Vec::new();
    
    // 시작 진행 상황
    let start_progress = DownloadProgress {
        channel: format!("벡터 임베딩 ({} 채널)", total_channels),
        status: "시작".to_string(),
        progress: 0.0,
        current_video: format!("선택된 {} 채널의 임베딩 생성 준비 중...", total_channels),
        total_videos: total_channels,
        completed_videos: 0,
        log_message: format!("🧠 {} 채널의 벡터 임베딩 생성을 시작합니다...", total_channels),
    };
    let _ = window.emit("embedding-progress", &start_progress);
    
    // 모든 선택된 채널을 한 번에 처리
    let processing_progress = DownloadProgress {
        channel: format!("벡터 임베딩 ({} 채널)", total_channels),
        status: "처리 중".to_string(),
        progress: 50.0,
        current_video: format!("📺 선택된 {} 채널 처리 중...", total_channels),
        total_videos: total_channels,
        completed_videos: 0,
        log_message: format!("📊 {} 채널의 벡터 임베딩 생성 중...", channels.join(", ")),
    };
    let _ = window.emit("embedding-progress", &processing_progress);
    
    // Python 스크립트 실행 (선택된 모든 채널을 한 번에 처리)
    let cmd = Command::new(&venv_python)
        .arg(&embed_script)
        .arg("channels")  // 특정 채널 모드
        .args(&channels)  // 선택된 채널들
        .current_dir(&project_root)
        .env("PYTHONUNBUFFERED", "1")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("스크립트 실행 실패: {}", e))?;
    
    // 실시간 출력 처리를 위한 BufReader 설정
    use std::io::{BufRead, BufReader};
    use std::sync::mpsc;
    use std::thread;
    
    let mut child = cmd;
    
    let stdout = child.stdout.take().unwrap();
    let stderr = child.stderr.take().unwrap();
    
    // stdout 실시간 처리 스레드
    let (tx, rx) = mpsc::channel();
    let tx_clone = tx.clone();
    
    thread::spawn(move || {
        let reader = BufReader::new(stdout);
        for line in reader.lines() {
            if let Ok(line) = line {
                let _ = tx.send(("stdout".to_string(), line));
            }
        }
    });
    
    // stderr 실시간 처리 스레드
    thread::spawn(move || {
        let reader = BufReader::new(stderr);
        for line in reader.lines() {
            if let Ok(line) = line {
                let _ = tx_clone.send(("stderr".to_string(), line));
            }
        }
    });
    
    // 실시간 로그 처리 루프
    let mut process_complete = false;
    while !process_complete {
        // 중단 확인
        if state.is_cancelled.load(Ordering::Relaxed) {
            let _ = child.kill();
            let _ = child.wait();
            
            let cancel_progress = DownloadProgress {
                channel: format!("벡터 임베딩 ({} 채널)", total_channels),
                status: "중단됨".to_string(),
                progress: 50.0,
                current_video: "사용자가 중단했습니다".to_string(),
                total_videos: total_channels,
                completed_videos: 0,
                log_message: "🛑 사용자가 임베딩 생성을 중단했습니다".to_string(),
            };
            let _ = window.emit("embedding-progress", &cancel_progress);
            return Ok(format!("임베딩 생성이 중단되었습니다."));
        }
        
        // 출력 받기 (타임아웃 설정)
        match rx.recv_timeout(std::time::Duration::from_millis(100)) {
            Ok((stream_type, line)) => {
                if !line.trim().is_empty() {
                    let log_progress = DownloadProgress {
                        channel: format!("벡터 임베딩 ({} 채널)", total_channels),
                        status: "처리 중".to_string(),
                        progress: 70.0,
                        current_video: "📺 임베딩 생성 중".to_string(),
                        total_videos: total_channels,
                        completed_videos: 0,
                        log_message: if stream_type == "stderr" { 
                            format!("⚠️ {}", line) 
                        } else { 
                            line.clone() 
                        },
                    };
                    let _ = window.emit("embedding-progress", &log_progress);
                    all_output.push(line);
                }
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {
                // 프로세스가 완료되었는지 확인
                match child.try_wait() {
                    Ok(Some(status)) => {
                        process_complete = true;
                        if !status.success() {
                            let error_progress = DownloadProgress {
                                channel: format!("벡터 임베딩 ({} 채널)", total_channels),
                                status: "실패".to_string(),
                                progress: 0.0,
                                current_video: "❌ 임베딩 생성 실패".to_string(),
                                total_videos: total_channels,
                                completed_videos: 0,
                                log_message: "❌ Python 스크립트 실행 실패".to_string(),
                            };
                            let _ = window.emit("embedding-progress", &error_progress);
                            return Err("임베딩 생성 실패".to_string());
                        }
                    }
                    Ok(None) => {
                        // 아직 실행 중
                        continue;
                    }
                    Err(e) => {
                        return Err(format!("프로세스 상태 확인 실패: {}", e));
                    }
                }
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                // 스레드가 종료됨, 프로세스 완료 확인
                let _ = child.wait();
                process_complete = true;
            }
        }
    }
    
    // 현재 프로세스 정리
    {
        let mut process_guard = state.current_process.lock().unwrap();
        *process_guard = None;
    }
    
    if state.is_cancelled.load(Ordering::Relaxed) {
        return Ok(format!("임베딩 생성이 중단되었습니다. {}개 채널 완료", total_channels));
    }
    
    // 최종 완료
    let final_progress = DownloadProgress {
        channel: format!("벡터 임베딩 ({} 채널)", total_channels),
        status: "완료".to_string(),
        progress: 100.0,
        current_video: "모든 채널 임베딩 완료".to_string(),
        total_videos: total_channels,
        completed_videos: total_channels,
        log_message: format!("🎉 {}개 채널의 벡터 임베딩 생성이 완료되었습니다!", total_channels),
    };
    let _ = window.emit("embedding-progress", &final_progress);
    
    Ok(format!("✅ {}개 채널의 벡터 임베딩 생성 완료\n{}", total_channels, all_output.join("\n")))
}

// 임베딩 생성 중단
#[command]
async fn cancel_embedding(state: State<'_, EmbeddingState>) -> Result<(), String> {
    state.is_cancelled.store(true, Ordering::Relaxed);
    
    // 실행 중인 프로세스는 메인 루프에서 처리됨
    // 여기서는 중단 플래그만 설정
    
    Ok(())
}

// 벡터 임베딩 생성 (진행 상황 포함) - 기존 호환성 유지
#[command]
async fn create_embeddings_with_progress(window: Window) -> Result<String, String> {
    let project_root = get_project_root();
    let embed_script = project_root.join("vault").join("90_indices").join("embed.py");
    if !embed_script.exists() {
        return Err(format!("embed.py 스크립트를 찾을 수 없습니다: {}", embed_script.display()));
    }
    
    let venv_python = project_root.join("venv").join("bin").join("python");
    if !venv_python.exists() {
        return Err(format!("Python 가상환경이 설정되지 않았습니다: {}", venv_python.display()));
    }
    
    // 시작 진행 상황
    let start_progress = DownloadProgress {
        channel: "벡터 임베딩".to_string(),
        status: "시작".to_string(),
        progress: 0.0,
        current_video: "임베딩 생성 준비 중...".to_string(),
        total_videos: 1,
        completed_videos: 0,
        log_message: "🧠 벡터 임베딩 생성을 시작합니다...".to_string(),
    };
    let _ = window.emit("embedding-progress", &start_progress);
    
    // Python 스크립트 실행
    let output = Command::new(&venv_python)
        .arg(&embed_script)
        .current_dir(&project_root)
        .env("PYTHONUNBUFFERED", "1")
        .output()
        .map_err(|e| e.to_string())?;
    
    if output.status.success() {
        let stdout = String::from_utf8_lossy(&output.stdout);
        let final_progress = DownloadProgress {
            channel: "벡터 임베딩".to_string(),
            status: "완료".to_string(),
            progress: 100.0,
            current_video: "임베딩 생성 완료".to_string(),
            total_videos: 1,
            completed_videos: 1,
            log_message: "✅ 벡터 임베딩 생성 완료!".to_string(),
        };
        let _ = window.emit("embedding-progress", &final_progress);
        Ok(format!("✅ 벡터 임베딩 생성 완료\n{}", stdout))
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let error_progress = DownloadProgress {
            channel: "벡터 임베딩".to_string(),
            status: "실패".to_string(),
            progress: 0.0,
            current_video: "임베딩 생성 실패".to_string(),
            total_videos: 1,
            completed_videos: 0,
            log_message: format!("❌ 벡터 임베딩 생성 실패: {}", stderr),
        };
        let _ = window.emit("embedding-progress", &error_progress);
        Err(format!("벡터 임베딩 생성 실패: {}", stderr))
    }
}

// 기존 벡터 임베딩 함수 (호환성 유지)
#[command]
async fn create_embeddings() -> Result<String, String> {
    let project_root = get_project_root();
    let embed_script = project_root.join("vault").join("90_indices").join("embed.py");
    if !embed_script.exists() {
        return Err(format!("embed.py 스크립트를 찾을 수 없습니다: {}", embed_script.display()));
    }
    
    let venv_python = project_root.join("venv").join("bin").join("python");
    if !venv_python.exists() {
        return Err(format!("Python 가상환경이 설정되지 않았습니다: {}", venv_python.display()));
    }
    
    let output = Command::new(&venv_python)
        .arg(&embed_script)
        .current_dir(&project_root)
        .output()
        .map_err(|e| e.to_string())?;
    
    if output.status.success() {
        let stdout = String::from_utf8_lossy(&output.stdout);
        Ok(format!("✅ 벡터 임베딩 생성 완료\n{}", stdout))
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(format!("벡터 임베딩 생성 실패: {}", stderr))
    }
}

// 벡터 검색
#[command]
async fn vector_search(query: String) -> Result<String, String> {
    let project_root = get_project_root();
    let embed_script = project_root.join("vault").join("90_indices").join("embed.py");
    if !embed_script.exists() {
        return Err(format!("embed.py 스크립트를 찾을 수 없습니다: {}", embed_script.display()));
    }
    
    let venv_python = project_root.join("venv").join("bin").join("python");
    let output = Command::new(&venv_python)
        .args(&[embed_script.to_str().unwrap(), "search", &query])
        .current_dir(&project_root)
        .output()
        .map_err(|e| e.to_string())?;
    
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(format!("검색 실패: {}", stderr))
    }
}

// RAG 질문-답변
#[command]
async fn ask_rag(query: String) -> Result<String, String> {
    let project_root = get_project_root();
    let rag_script = project_root.join("vault").join("90_indices").join("rag.py");
    if !rag_script.exists() {
        return Err(format!("rag.py 스크립트를 찾을 수 없습니다: {}", rag_script.display()));
    }
    
    let venv_python = project_root.join("venv").join("bin").join("python");
    let output = Command::new(&venv_python)
        .args(&[rag_script.to_str().unwrap(), &query])
        .current_dir(&project_root)
        .output()
        .map_err(|e| e.to_string())?;
    
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(format!("RAG 질문 실패: {}", stderr))
    }
}



// 채널별 AI 질문 (DeepSeek, 실시간 진행 상황 포함)
#[command]
async fn ask_ai_with_progress(window: Window, query: String, channel_name: String, model: String) -> Result<String, String> {
    let project_root = get_project_root();
    let rag_script = project_root.join("vault").join("90_indices").join("rag.py");
    
    if !rag_script.exists() {
        return Err("RAG 스크립트를 찾을 수 없습니다".to_string());
    }

    // 초기 진행 상황 전송
    let _ = window.emit("ai-progress", AIProgressUpdate {
        step: "초기화".to_string(),
        message: "🔍 검색 준비 중...".to_string(),
        progress: 0.0,
        details: Some(format!("채널: {} | 모델: {}", channel_name, model)),
    });

    let venv_python = project_root.join("venv").join("bin").join("python");
    let mut child = Command::new(&venv_python)
        .args(&[rag_script.to_str().unwrap(), &query, &channel_name, "--progress", "--model", &model])
        .current_dir(&project_root)
        .env("PYTHONUNBUFFERED", "1")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| e.to_string())?;

    let stdout = child.stdout.take().unwrap();
    let reader = BufReader::new(stdout);
    let mut result = String::new();
    let mut is_final_answer = false;

    // 실시간 출력 처리
    for line in reader.lines() {
        let line = line.map_err(|e| e.to_string())?;
        
        // 진행 상황 파싱
        if line.starts_with("PROGRESS:") {
            if let Some(progress_json) = line.strip_prefix("PROGRESS:") {
                if let Ok(progress_data) = serde_json::from_str::<AIProgressUpdate>(progress_json) {
                    let _ = window.emit("ai-progress", progress_data);
                }
            }
        }
        // 최종 답변 시작 표시
        else if line.starts_with("FINAL_ANSWER:") {
            is_final_answer = true;
            let _ = window.emit("ai-progress", AIProgressUpdate {
                step: "완료".to_string(),
                message: "✅ 답변 생성 완료".to_string(),
                progress: 100.0,
                details: None,
            });
        }
        // 최종 답변 수집
        else if is_final_answer {
            if !result.is_empty() {
                result.push('\n');
            }
            result.push_str(&line);
        }
    }

    let status = child.wait().map_err(|e| e.to_string())?;
    
    if status.success() {
        if result.is_empty() {
            // 진행 상황 없이 기본 방식으로 실행된 경우
            let output = Command::new(&venv_python)
                .args(&[rag_script.to_str().unwrap(), &query, &channel_name, "--model", &model])
                .current_dir(&project_root)
                .env("PYTHONUNBUFFERED", "1")
                .output()
                .map_err(|e| e.to_string())?;
            
            if output.status.success() {
                Ok(String::from_utf8_lossy(&output.stdout).to_string())
            } else {
                let stderr = String::from_utf8_lossy(&output.stderr);
                Err(format!("DeepSeek RAG 질문 실패: {}", stderr))
            }
        } else {
            Ok(result)
        }
    } else {
        let stderr_output = Command::new(&venv_python)
            .args(&[rag_script.to_str().unwrap(), &query, &channel_name, "--model", &model])
            .current_dir(&project_root)
            .stderr(Stdio::piped())
            .output()
            .map_err(|e| e.to_string())?;
        
        let stderr = String::from_utf8_lossy(&stderr_output.stderr);
        Err(format!("DeepSeek RAG 질문 실패: {}", stderr))
    }
}



// AI 질문 (실시간 진행 상황 포함)
#[command]
async fn ask_ai_universal_with_progress(window: Window, query: String, channel_name: String, model: String) -> Result<String, String> {
    ask_ai_with_progress(window, query, channel_name, model).await
}

#[derive(Serialize, Deserialize)]
struct AIChannelInfo {
    name: String,
    video_count: u32,
    description: Option<String>,
    last_updated: Option<String>,
}



// AI용 채널 목록 조회
#[command]
async fn get_available_channels_for_ai() -> Result<Vec<AIChannelInfo>, String> {
    let project_root = get_project_root();
    let rag_script = project_root.join("vault").join("90_indices").join("rag.py");
    
    if !rag_script.exists() {
        return Ok(vec![]);
    }
    
    let venv_python = project_root.join("venv").join("bin").join("python");
    let output = Command::new(&venv_python)
        .args(&[rag_script.to_str().unwrap(), "channels"])
        .current_dir(&project_root)
        .output()
        .map_err(|e| e.to_string())?;
    
    if output.status.success() {
        let stdout = String::from_utf8_lossy(&output.stdout);
        // 간단한 파싱으로 채널 목록 반환
        let channels = parse_channel_list(&stdout);
        Ok(channels)
    } else {
        Err("채널 목록 조회 실패".to_string())
    }
}

fn parse_channel_list(output: &str) -> Vec<AIChannelInfo> {
    let mut channels = Vec::new();
    
    println!("파싱할 출력:\n{}", output);
    
    // "1. channel_name (X개 영상)" 형태의 라인을 파싱 (이모지 및 기타 텍스트 무시)
    for line in output.lines() {
        println!("파싱 중인 라인: {}", line);
        if let Some(captures) = regex::Regex::new(r"^\s*\d+\.\s*(.+?)\s*\((\d+)개\s*영상\)")
            .ok()
            .and_then(|re| re.captures(line))
        {
            if let (Some(name), Some(count_str)) = (captures.get(1), captures.get(2)) {
                if let Ok(count) = count_str.as_str().parse::<u32>() {
                    println!("파싱 성공: {} - {}개", name.as_str().trim(), count);
                    channels.push(AIChannelInfo {
                        name: name.as_str().trim().to_string(),
                        video_count: count,
                        description: None,
                        last_updated: None,
                    });
                }
            }
        }
    }
    
    println!("파싱된 채널 개수: {}", channels.len());
    channels
}

// 채널별 프롬프트 조회
#[command]
async fn get_channel_prompt(channel_name: String) -> Result<String, String> {
    let project_root = get_project_root();
    let prompts_dir = project_root.join("vault").join("90_indices").join("prompts");
    
    // 채널명을 파일시스템에 안전한 형태로 변환
    let safe_channel_name = sanitize_channel_name(&channel_name);
    let channel_dir = prompts_dir.join(&safe_channel_name);
    
    if !channel_dir.exists() {
        return Ok("{}".to_string()); // 기본 프롬프트 반환
    }
    
    // 활성 버전 확인
    let active_file = channel_dir.join("active.txt");
    let version = if active_file.exists() {
        std::fs::read_to_string(&active_file)
            .map_err(|e| e.to_string())?
            .trim()
            .parse::<u32>()
            .unwrap_or(1)
    } else {
        1
    };
    
    // 프롬프트 파일 읽기
    let prompt_file = channel_dir.join(format!("prompt_v{}.json", version));
    if prompt_file.exists() {
        std::fs::read_to_string(&prompt_file).map_err(|e| e.to_string())
    } else {
        Ok("{}".to_string())
    }
}

fn sanitize_channel_name(name: &str) -> String {
    // 특수문자를 밑줄로 변경하고 길이 제한
    let sanitized = name
        .chars()
        .map(|c| if c.is_alphanumeric() || "가나다라마바사아자차카타파하".contains(c) || c == '_' || c == '-' {
            c
        } else {
            '_'
        })
        .collect::<String>();
    
    // 연속된 밑줄 제거
    let re = regex::Regex::new(r"_+").unwrap();
    let result = re.replace_all(&sanitized, "_");
    
    // 앞뒤 밑줄 제거하고 길이 제한
    result.trim_matches('_').chars().take(50).collect()
}

// 채널별 자동 프롬프트 생성
#[command]
async fn auto_generate_channel_prompt(channel_name: String) -> Result<u32, String> {
    let project_root = get_project_root();
    let auto_prompt_script = project_root.join("vault").join("90_indices").join("auto_prompt.py");
    
    if !auto_prompt_script.exists() {
        return Err("자동 프롬프트 생성 스크립트를 찾을 수 없습니다".to_string());
    }
    
    let venv_python = project_root.join("venv").join("bin").join("python");
    let output = Command::new(&venv_python)
        .args(&[auto_prompt_script.to_str().unwrap(), "generate", &channel_name])
        .current_dir(&project_root)
        .output()
        .map_err(|e| e.to_string())?;
    
    if output.status.success() {
        let stdout = String::from_utf8_lossy(&output.stdout);
        // 버전 번호 추출 (예: "v3 생성 완료" -> 3)
        if let Some(version_match) = stdout.find("v") {
            if let Some(space_pos) = stdout[version_match..].find(" ") {
                let version_str = &stdout[version_match + 1..version_match + space_pos];
                if let Ok(version) = version_str.parse::<u32>() {
                    return Ok(version);
                }
            }
        }
        Ok(1) // 기본값
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(format!("자동 프롬프트 생성 실패: {}", stderr))
    }
}

// 채널 분석 결과 조회
#[command]
async fn get_channel_analysis(channel_name: String) -> Result<String, String> {
    let project_root = get_project_root();
    let auto_prompt_script = project_root.join("vault").join("90_indices").join("auto_prompt.py");
    
    let venv_python = project_root.join("venv").join("bin").join("python");
    let output = Command::new(&venv_python)
        .args(&[auto_prompt_script.to_str().unwrap(), "analyze", &channel_name])
        .current_dir(&project_root)
        .output()
        .map_err(|e| e.to_string())?;
    
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(format!("채널 분석 실패: {}", stderr))
    }
}

// 모든 채널 자동 프롬프트 일괄 생성
#[command]
async fn batch_generate_prompts() -> Result<String, String> {
    let project_root = get_project_root();
    let auto_prompt_script = project_root.join("vault").join("90_indices").join("auto_prompt.py");
    
    let venv_python = project_root.join("venv").join("bin").join("python");
    let output = Command::new(&venv_python)
        .args(&[auto_prompt_script.to_str().unwrap(), "batch"])
        .current_dir(&project_root)
        .output()
        .map_err(|e| e.to_string())?;
    
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(format!("일괄 프롬프트 생성 실패: {}", stderr))
    }
}

// 채널별 프롬프트 저장
#[command]
async fn save_channel_prompt(channel_name: String, prompt_data: String) -> Result<u32, String> {
    let project_root = get_project_root();
    let prompts_dir = project_root.join("vault").join("90_indices").join("prompts");
    
    let safe_channel_name = sanitize_channel_name(&channel_name);
    let channel_dir = prompts_dir.join(&safe_channel_name);
    
    // 디렉토리 생성
    std::fs::create_dir_all(&channel_dir).map_err(|e| e.to_string())?;
    
    // 기존 버전 확인
    let existing_versions: Vec<u32> = std::fs::read_dir(&channel_dir)
        .map_err(|e| e.to_string())?
        .filter_map(|entry| {
            let entry = entry.ok()?;
            let filename = entry.file_name().to_string_lossy().to_string();
            if filename.starts_with("prompt_v") && filename.ends_with(".json") {
                let version_str = filename.strip_prefix("prompt_v")?.strip_suffix(".json")?;
                version_str.parse().ok()
            } else {
                None
            }
        })
        .collect();
    
    let new_version = existing_versions.iter().max().unwrap_or(&0) + 1;
    
    // 새 프롬프트 파일 저장
    let prompt_file = channel_dir.join(format!("prompt_v{}.json", new_version));
    std::fs::write(&prompt_file, &prompt_data).map_err(|e| e.to_string())?;
    
    // 활성 버전 업데이트
    let active_file = channel_dir.join("active.txt");
    std::fs::write(&active_file, new_version.to_string()).map_err(|e| e.to_string())?;
    
    Ok(new_version)
}

// 프롬프트 버전 목록 조회
#[command]
async fn get_prompt_versions(channel_name: String) -> Result<String, String> {
    let project_root = get_project_root();
    let auto_prompt_script = project_root.join("vault").join("90_indices").join("auto_prompt.py");
    
    let venv_python = project_root.join("venv").join("bin").join("python");
    let output = Command::new(&venv_python)
        .args(&[auto_prompt_script.to_str().unwrap(), "versions", &channel_name])
        .current_dir(&project_root)
        .output()
        .map_err(|e| e.to_string())?;
    
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(format!("프롬프트 버전 조회 실패: {}", stderr))
    }
}

// 프롬프트 현황 조회
#[command]
async fn get_prompt_status() -> Result<String, String> {
    let project_root = get_project_root();
    let auto_prompt_script = project_root.join("vault").join("90_indices").join("auto_prompt.py");
    
    let venv_python = project_root.join("venv").join("bin").join("python");
    let output = Command::new(&venv_python)
        .args(&[auto_prompt_script.to_str().unwrap(), "status"])
        .current_dir(&project_root)
        .output()
        .map_err(|e| e.to_string())?;
    
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(format!("프롬프트 현황 조회 실패: {}", stderr))
    }
}

// 데이터 정합성 검사 (진행 상황 포함)
#[command]
async fn check_integrity_with_progress(window: Window) -> Result<String, String> {
    let project_root = get_project_root();
    let venv_python = project_root.join("venv").join("bin").join("python");
    if !venv_python.exists() {
        return Err(format!("Python 가상환경이 설정되지 않았습니다: {}", venv_python.display()));
    }
    
    // 시작 진행 상황
    let start_progress = DownloadProgress {
        channel: "정합성 검사".to_string(),
        status: "시작".to_string(),
        progress: 0.0,
        current_video: "검사 준비 중...".to_string(),
        total_videos: 1,
        completed_videos: 0,
        log_message: "🔍 데이터 정합성 검사를 시작합니다...".to_string(),
    };
    let _ = window.emit("integrity-progress", &start_progress);
    
    // 진행률 업데이트 (25% - 시작)
    let progress_25 = DownloadProgress {
        channel: "정합성 검사".to_string(),
        status: "시작".to_string(),
        progress: 25.0,
        current_video: "검사 스크립트 실행 중...".to_string(),
        total_videos: 1,
        completed_videos: 0,
        log_message: "🔍 데이터 정합성 검사 스크립트 실행 중...".to_string(),
    };
    let _ = window.emit("integrity-progress", &progress_25);
    
    // 진행률 업데이트 (50% - 검사 중)
    let progress_50 = DownloadProgress {
        channel: "정합성 검사".to_string(),
        status: "검사 중".to_string(),
        progress: 50.0,
        current_video: "파일 검사 중...".to_string(),
        total_videos: 1,
        completed_videos: 0,
        log_message: "📁 Vault 파일 구조 및 메타데이터 검사 중...".to_string(),
    };
    let _ = window.emit("integrity-progress", &progress_50);
    
    // 새로운 채널별 격리 정합성 검사 스크립트 실행 (실시간 로그)
    let integrity_script = project_root.join("vault").join("90_indices").join("integrity_check.py");
    if !integrity_script.exists() {
        return Err(format!("정합성 검사 스크립트를 찾을 수 없습니다: {}", integrity_script.display()));
    }
    
    let mut child = Command::new(&venv_python)
        .arg(&integrity_script)
        .current_dir(&project_root)
        .env("PYTHONUNBUFFERED", "1")
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .map_err(|e| e.to_string())?;
    
    let stdout = child.stdout.take().ok_or("stdout를 가져올 수 없습니다")?;
    let stderr = child.stderr.take().ok_or("stderr를 가져올 수 없습니다")?;
    
    // 별도 스레드에서 실시간 로그 처리
    let window_clone = window.clone();
    std::thread::spawn(move || {
        let stdout_reader = std::io::BufReader::new(stdout);
        for line in stdout_reader.lines() {
            if let Ok(line) = line {
                let line = line.trim();
                if !line.is_empty() {
                    let progress = DownloadProgress {
                        channel: "정합성 검사".to_string(),
                        status: "검사 중".to_string(),
                        progress: 75.0,
                        current_video: "실시간 검사 중...".to_string(),
                        total_videos: 1,
                        completed_videos: 0,
                        log_message: line.to_string(),
                    };
                    let _ = window_clone.emit("integrity-progress", &progress);
                }
            }
        }
    });
    
    let window_clone2 = window.clone();
    std::thread::spawn(move || {
        let stderr_reader = std::io::BufReader::new(stderr);
        for line in stderr_reader.lines() {
            if let Ok(line) = line {
                let line = line.trim();
                if !line.is_empty() {
                    let progress = DownloadProgress {
                        channel: "정합성 검사".to_string(),
                        status: "경고".to_string(),
                        progress: 75.0,
                        current_video: "실시간 검사 중...".to_string(),
                        total_videos: 1,
                        completed_videos: 0,
                        log_message: format!("⚠️ {}", line),
                    };
                    let _ = window_clone2.emit("integrity-progress", &progress);
                }
            }
        }
    });
    
    // 프로세스 완료 대기
    let output = child.wait_with_output().map_err(|e| e.to_string())?;
    
    // 진행률 업데이트 (75% - 거의 완료)
    let progress_75 = DownloadProgress {
        channel: "정합성 검사".to_string(),
        status: "완료 중".to_string(),
        progress: 75.0,
        current_video: "검사 결과 정리 중...".to_string(),
        total_videos: 1,
        completed_videos: 0,
        log_message: "📋 검사 결과 정리 및 보고서 생성 중...".to_string(),
    };
    let _ = window.emit("integrity-progress", &progress_75);
    
    if output.status.success() {
        let stdout = String::from_utf8_lossy(&output.stdout);
        let final_progress = DownloadProgress {
            channel: "정합성 검사".to_string(),
            status: "완료".to_string(),
            progress: 100.0,
            current_video: "검사 완료".to_string(),
            total_videos: 1,
            completed_videos: 1,
            log_message: "✅ 데이터 정합성 검사 완료!".to_string(),
        };
        let _ = window.emit("integrity-progress", &final_progress);
        Ok(format!("✅ 데이터 정합성 검사 완료\n{}", stdout))
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let error_progress = DownloadProgress {
            channel: "정합성 검사".to_string(),
            status: "실패".to_string(),
            progress: 0.0,
            current_video: "검사 실패".to_string(),
            total_videos: 1,
            completed_videos: 0,
            log_message: format!("❌ 데이터 정합성 검사 실패: {}", stderr),
        };
        let _ = window.emit("integrity-progress", &error_progress);
        Err(format!("데이터 정합성 검사 실패: {}", stderr))
    }
}

// 기존 데이터 정합성 검사 함수 (호환성 유지)
#[command]
async fn check_integrity() -> Result<String, String> {
    let project_root = get_project_root();
    let venv_python = project_root.join("venv").join("bin").join("python");
    if !venv_python.exists() {
        return Err(format!("Python 가상환경이 설정되지 않았습니다: {}", venv_python.display()));
    }
    
    let integrity_script = project_root.join("vault").join("90_indices").join("integrity_check.py");
    if !integrity_script.exists() {
        return Err(format!("정합성 검사 스크립트를 찾을 수 없습니다: {}", integrity_script.display()));
    }
    
    let output = Command::new(&venv_python)
        .arg(&integrity_script)
        .current_dir(&project_root)
        .output()
        .map_err(|e| e.to_string())?;
    
    if output.status.success() {
        let stdout = String::from_utf8_lossy(&output.stdout);
        Ok(format!("✅ 데이터 정합성 검사 완료\n{}", stdout))
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(format!("데이터 정합성 검사 실패: {}", stderr))
    }
}

// 앱 상태 조회
#[command]
fn get_app_status() -> Result<AppStatus, String> {
    let project_root = get_project_root();
    let vault_path = project_root.join("vault");
    let channels = list_channels().unwrap_or_default();
    let videos = list_videos().unwrap_or_default();
    
    // Vault 크기 계산 (MB 단위로 반환)
    let vault_size_bytes = calculate_directory_size(&vault_path);
    let vault_size_mb = vault_size_bytes as f64 / (1024.0 * 1024.0);
    
    // 벡터 DB 상태 확인
    let chroma_path = project_root.join("vault").join("90_indices").join("chroma");
    let vector_db_status = if chroma_path.exists() {
        "활성화됨".to_string()
    } else {
        "비활성화됨".to_string()
    };
    
    // 마지막 다운로드 시간 (구현 필요)
    let last_download = None; // TODO: 실제 구현
    
    Ok(AppStatus {
        total_videos: videos.len() as u32,
        total_channels: channels.len() as u32,
        vault_size_mb: vault_size_mb,
        last_download,
        vector_db_status,
    })
}

fn calculate_directory_size(path: &PathBuf) -> u64 {
    if !path.exists() {
        return 0;
    }
    
    let mut size = 0;
    if let Ok(entries) = fs::read_dir(path) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_file() {
                if let Ok(metadata) = fs::metadata(&path) {
                    size += metadata.len();
                }
            } else if path.is_dir() {
                size += calculate_directory_size(&path);
            }
        }
    }
    size
}

// 채널별로 전체 비디오를 그룹핑하여 조회 (인기/최신 분리)
#[command]
fn get_recent_videos_by_channel(limit_per_channel: Option<usize>) -> Result<RecentVideos, String> {
    let videos = list_videos()?;
    let _limit = limit_per_channel.unwrap_or(5);
    
    // 채널별로 그룹핑 (전체 비디오)
    let mut channel_groups: HashMap<String, Vec<VideoInfo>> = HashMap::new();
    
    for video in videos {
        let channel_name = video.channel.clone();
        channel_groups.entry(channel_name).or_insert_with(Vec::new).push(video);
    }
    
    // 각 채널의 전체 비디오를 반환 (프론트엔드에서 인기/최신 분리)
    let mut channels: Vec<ChannelVideos> = channel_groups
        .into_iter()
        .map(|(channel_name, videos)| {
            ChannelVideos {
                channel_name,
                videos,
            }
        })
        .collect();
    
    // 채널을 이름순으로 정렬
    channels.sort_by(|a, b| a.channel_name.cmp(&b.channel_name));
    
    Ok(RecentVideos { channels })
}

// 설정 관리
#[command]
fn get_config() -> Result<String, String> {
    let project_root = get_project_root();
    let config_path = project_root.join("pyproject.toml");
    if config_path.exists() {
        fs::read_to_string(&config_path).map_err(|e| e.to_string())
    } else {
        Ok("설정 파일이 없습니다".to_string())
    }
}

// Range 요청을 지원하는 비디오 서버 시작
#[command]
async fn start_video_server(state: State<'_, VideoServerState>) -> Result<u16, String> {
    let server_port_lock = state.server_port.read().await;
    
    // 이미 서버가 실행 중이면 포트 반환
    if let Some(port) = *server_port_lock {
        return Ok(port);
    }
    drop(server_port_lock);
    
    let project_root = get_project_root();
    
    // 사용 가능한 포트 찾기 (OS가 자동 할당)
    let port = find_available_port().await?;
    
    // Range 지원 파일 서빙 필터 생성
    let files = warp::path("video")
        .and(warp::path::tail())
        .and(warp::get())
        .and(warp::header::optional::<String>("range"))
        .and_then(move |tail: warp::path::Tail, range: Option<String>| {
            let project_root = project_root.clone();
            async move {
                serve_video_with_range(project_root, tail.as_str(), range).await
            }
        });
    
    // CORS 헤더 추가 (로컬 전용)
    let cors = warp::cors()
        .allow_origin("tauri://localhost")
        .allow_origin("http://localhost:3000") // 개발용
        .allow_headers(vec!["content-type", "range"])
        .allow_methods(vec!["GET", "HEAD", "OPTIONS"]);
    
    let routes = files.with(cors);
    
    // 서버 시작 (127.0.0.1 바인딩으로 보안 강화)
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let server = warp::serve(routes).run(addr);
    
    let handle = tokio::spawn(server);
    
    // 상태 업데이트
    *state.server_port.write().await = Some(port);
    *state.server_handle.write().await = Some(handle);
    
    Ok(port)
}

// Range 요청을 지원하는 비디오 파일 서빙
async fn serve_video_with_range(
    project_root: PathBuf, 
    file_path: &str, 
    range_header: Option<String>
) -> Result<impl warp::Reply, warp::Rejection> {
    use warp::http::StatusCode;
    use std::io::{Read, Seek, SeekFrom};
    
    // 보안: 경로 탐색 공격 방지
    let cleaned_path = file_path.replace("..", "");
    let safe_path = cleaned_path.trim_start_matches('/');
    
    // URL 디코딩 처리
    let decoded_path = match urlencoding::decode(safe_path) {
        Ok(decoded) => decoded.to_string(),
        Err(_) => safe_path.to_string()
    };
    
    // vault/ 경로를 올바르게 매핑
    let full_path = project_root.join("vault").join(&decoded_path);
    
    if !full_path.exists() || !full_path.is_file() {
        return Err(warp::reject::not_found());
    }
    
    // MIME 타입 추정 (비디오 파일에 대해 명시적으로 설정)
    let mime_type = if full_path.extension().map(|ext| ext == "mp4").unwrap_or(false) {
        "video/mp4".to_string()
    } else {
        mime_guess::from_path(&full_path)
            .first_or_octet_stream()
            .to_string()
    };
    
    // 파일 크기 확인
    let file_size = match std::fs::metadata(&full_path) {
        Ok(metadata) => metadata.len(),
        Err(_) => return Err(warp::reject::not_found()),
    };
    
    // Range 헤더 파싱
    let (start, end) = parse_range_header(range_header.as_deref(), file_size);
    let content_length = end - start + 1;
    
    // 파일 읽기
    let mut file = match std::fs::File::open(&full_path) {
        Ok(f) => f,
        Err(_) => return Err(warp::reject::not_found()),
    };
    
    // 시작 위치로 이동
    if let Err(_) = file.seek(SeekFrom::Start(start)) {
        return Err(warp::reject::not_found());
    }
    
    // 요청된 범위만큼 읽기
    let mut buffer = vec![0u8; content_length as usize];
    if let Err(_) = file.read_exact(&mut buffer) {
        return Err(warp::reject::not_found());
    }
    
    // HTTP 응답 생성 (warp::reply::Response 사용)
    use warp::http::Response;
    
    let status_code = if range_header.is_some() && (start != 0 || end + 1 != file_size) {
        StatusCode::PARTIAL_CONTENT
    } else {
        StatusCode::OK
    };
    
    let mut response_builder = Response::builder()
        .status(status_code)
        .header("content-type", mime_type)
        .header("accept-ranges", "bytes")
        .header("access-control-allow-origin", "*")
        .header("access-control-allow-methods", "GET, HEAD, OPTIONS")
        .header("access-control-allow-headers", "range")
        .header("cache-control", "no-cache");
    
    if range_header.is_some() && (start != 0 || end + 1 != file_size) {
        response_builder = response_builder
            .header("content-range", format!("bytes {}-{}/{}", start, end, file_size))
            .header("content-length", content_length.to_string());
    } else {
        response_builder = response_builder
            .header("content-length", file_size.to_string());
    }
    
         match response_builder.body(buffer) {
         Ok(response) => Ok(response),
         Err(_) => Err(warp::reject::custom(ServerError)),
     }
}

// Range 헤더 파싱 함수
fn parse_range_header(range_header: Option<&str>, file_size: u64) -> (u64, u64) {
    if let Some(range) = range_header {
        if let Some(range_value) = range.strip_prefix("bytes=") {
            if let Some((start_str, end_str)) = range_value.split_once('-') {
                let start = start_str.parse::<u64>().unwrap_or(0);
                let end = if end_str.is_empty() {
                    file_size - 1
                } else {
                    end_str.parse::<u64>().unwrap_or(file_size - 1).min(file_size - 1)
                };
                return (start, end);
            }
        }
    }
    (0, file_size - 1)
}

// 사용 가능한 포트 찾기
async fn find_available_port() -> Result<u16, String> {
    use std::net::TcpListener;
    
    // OS가 자동으로 할당하는 방식 (포트 0 사용)
    match TcpListener::bind("127.0.0.1:0") {
        Ok(listener) => {
            let port = listener.local_addr().unwrap().port();
            drop(listener); // 바로 해제
            Ok(port)
        }
        Err(_) => {
            // fallback: 수동으로 포트 검색
            for port in 8080..8090 {
                if TcpListener::bind(format!("127.0.0.1:{}", port)).is_ok() {
                    return Ok(port);
                }
            }
            Err("사용 가능한 포트를 찾을 수 없습니다".to_string())
        }
    }
}

// 비디오 서버 중지
#[command]
async fn stop_video_server(state: State<'_, VideoServerState>) -> Result<(), String> {
    let mut server_handle_lock = state.server_handle.write().await;
    let mut server_port_lock = state.server_port.write().await;
    
    if let Some(handle) = server_handle_lock.take() {
        handle.abort();
    }
    
    *server_port_lock = None;
    
    Ok(())
}

// 비디오 서버 상태 확인
#[command]
async fn get_video_server_status(state: State<'_, VideoServerState>) -> Result<Option<u16>, String> {
    let server_port_lock = state.server_port.read().await;
    Ok(*server_port_lock)
}

// 비디오 URL 생성
#[command]
async fn get_video_url(video_path: String, state: State<'_, VideoServerState>) -> Result<String, String> {
    let server_port_lock = state.server_port.read().await;
    
    if let Some(port) = *server_port_lock {
        // vault/ 경로 제거하고 HTTP URL 생성
        let clean_path = video_path.trim_start_matches("vault/");
        
        // URL 인코딩 처리 - 특수문자와 한글 문자 처리
        let encoded_path = urlencoding::encode(clean_path).to_string();
        
        Ok(format!("http://127.0.0.1:{}/video/{}", port, encoded_path))
    } else {
        Err("비디오 서버가 실행되지 않았습니다. 먼저 서버를 시작해주세요.".to_string())
    }
}

// 시스템 플레이어로 비디오 열기
#[command]
async fn open_in_system_player(video_path: String) -> Result<(), String> {
    let project_root = get_project_root();
    let full_path = project_root.join(&video_path);
    
    if !full_path.exists() {
        return Err(format!("비디오 파일을 찾을 수 없습니다: {}", full_path.display()));
    }
    
    // 운영체제별 명령어 실행
    #[cfg(target_os = "macos")]
    {
        Command::new("open")
            .arg(&full_path)
            .spawn()
            .map_err(|e| format!("macOS 시스템 플레이어 실행 실패: {}", e))?;
    }
    
    #[cfg(target_os = "windows")]
    {
        Command::new("cmd")
            .args(&["/C", "start", "", &full_path.to_string_lossy()])
            .spawn()
            .map_err(|e| format!("Windows 시스템 플레이어 실행 실패: {}", e))?;
    }
    
    #[cfg(target_os = "linux")]
    {
        Command::new("xdg-open")
            .arg(&full_path)
            .spawn()
            .map_err(|e| format!("Linux 시스템 플레이어 실행 실패: {}", e))?;
    }
    
    println!("🎬 시스템 플레이어로 비디오 열기: {}", full_path.display());
    Ok(())
}

// 비디오 변환 관련 함수들

#[command]
async fn convert_video_file(
    window: Window,
    video_path: String, 
    quality: String,
    codec: String,
    backup: bool,
    state: State<'_, ConversionState>
) -> Result<String, String> {
    // 이미 변환 중인지 확인
    if state.is_converting.load(Ordering::Relaxed) {
        return Err("이미 변환이 진행 중입니다".to_string());
    }
    
    let project_root = get_project_root();
    let video_full_path = project_root.join(&video_path);
    
    if !video_full_path.exists() {
        return Err(format!("비디오 파일을 찾을 수 없습니다: {}", video_full_path.display()));
    }
    
    // 변환 시작
    state.is_converting.store(true, Ordering::Relaxed);
    
    // Python 가상환경 경로 찾기
    let venv_path = project_root.join("venv");
    let python_path = if venv_path.exists() {
        #[cfg(target_os = "windows")]
        {
            venv_path.join("Scripts").join("python.exe")
        }
        #[cfg(not(target_os = "windows"))]
        {
            venv_path.join("bin").join("python")
        }
    } else {
        PathBuf::from("python")
    };
    
    // ydh convert-single 명령어 구성
    let mut cmd = Command::new(&python_path);
    cmd.arg("-m")
       .arg("ydh")
       .arg("convert-single")
       .arg(&video_full_path)
       .arg("--quality")
       .arg(&quality)
       .arg("--codec")
       .arg(&codec);
    
    if backup {
        cmd.arg("--backup");
    } else {
        cmd.arg("--no-backup");
    }
    
    cmd.current_dir(&project_root)
       .stdout(Stdio::piped())
       .stderr(Stdio::piped());
    
    // 명령어 실행
    let child = cmd.spawn().map_err(|e| {
        state.is_converting.store(false, Ordering::Relaxed);
        format!("Python 프로세스 시작 실패: {}", e)
    })?;
    
    // 프로세스 저장
    {
        let mut process_guard = state.current_process.lock().unwrap();
        *process_guard = Some(child);
    }
    
    // 별도 스레드에서 출력 모니터링
    let window_clone = window.clone();
    let state_clone = state.inner().clone();
    let video_path_clone = video_path.clone();
    
    tokio::spawn(async move {
        let mut child = {
            let mut process_guard = state_clone.current_process.lock().unwrap();
            process_guard.take()
        }.unwrap();
        
        // stderr에서 출력 읽기 (FFmpeg 출력)
        if let Some(stderr) = child.stderr.take() {
            let reader = BufReader::new(stderr);
            
            for line in reader.lines() {
                if let Ok(line) = line {
                    // 변환 진행 상황 파싱
                    let progress = parse_conversion_progress(&line);
                    
                    let conversion_progress = DownloadProgress {
                        channel: "변환".to_string(),
                        status: "변환 중".to_string(),
                        progress,
                        current_video: video_path_clone.clone(),
                        total_videos: 1,
                        completed_videos: 0,
                        log_message: line,
                    };
                    
                    let _ = window_clone.emit("conversion-progress", &conversion_progress);
                }
                
                // 변환 중단 확인
                if state_clone.is_converting.load(Ordering::Relaxed) == false {
                    let _ = child.kill();
                    break;
                }
            }
        }
        
        // 프로세스 완료 대기
        let result = child.wait();
        
        let final_progress = match result {
            Ok(status) if status.success() => {
                DownloadProgress {
                    channel: "변환".to_string(),
                    status: "완료".to_string(),
                    progress: 100.0,
                    current_video: video_path_clone.clone(),
                    total_videos: 1,
                    completed_videos: 1,
                    log_message: "✅ 비디오 변환 완료!".to_string(),
                }
            },
            _ => {
                DownloadProgress {
                    channel: "변환".to_string(),
                    status: "실패".to_string(),
                    progress: 0.0,
                    current_video: video_path_clone.clone(),
                    total_videos: 1,
                    completed_videos: 0,
                    log_message: "❌ 비디오 변환 실패".to_string(),
                }
            }
        };
        
        let _ = window_clone.emit("conversion-progress", &final_progress);
        
        // 변환 상태 초기화
        state_clone.is_converting.store(false, Ordering::Relaxed);
    });
    
    Ok("비디오 변환이 시작되었습니다".to_string())
}

#[command]
async fn cancel_conversion(state: State<'_, ConversionState>) -> Result<(), String> {
    state.is_converting.store(false, Ordering::Relaxed);
    
    if let Ok(mut process_guard) = state.current_process.lock() {
        if let Some(mut child) = process_guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
    
    Ok(())
}

#[command]
async fn get_conversion_status(state: State<'_, ConversionState>) -> Result<bool, String> {
    Ok(state.is_converting.load(Ordering::Relaxed))
}

// FFmpeg 출력에서 변환 진행률 파싱
fn parse_conversion_progress(line: &str) -> f32 {
    // FFmpeg 시간 출력 파싱: time=00:01:23.45
    if let Some(captures) = Regex::new(r"time=(\d{2}):(\d{2}):(\d{2})\.(\d+)").unwrap().captures(line) {
        if let (Some(hours), Some(minutes), Some(seconds)) = 
            (captures.get(1), captures.get(2), captures.get(3)) {
            if let (Ok(h), Ok(m), Ok(s)) = 
                (hours.as_str().parse::<f32>(), minutes.as_str().parse::<f32>(), seconds.as_str().parse::<f32>()) {
                let total_seconds = h * 3600.0 + m * 60.0 + s;
                // 예상 총 시간을 모르므로 임시로 무한 진행률 대신 시간만 반환
                // 실제로는 비디오 길이를 알아야 정확한 퍼센트 계산 가능
                return (total_seconds / 10.0).min(95.0); // 임시 계산
            }
        }
    }
    
    // FFmpeg 프레임 출력: frame= 1234
    if let Some(captures) = Regex::new(r"frame=\s*(\d+)").unwrap().captures(line) {
        if let Some(frame_match) = captures.get(1) {
            if let Ok(frame) = frame_match.as_str().parse::<f32>() {
                return (frame / 100.0).min(95.0); // 임시 계산
            }
        }
    }
    
    -1.0 // 진행률을 파싱할 수 없는 경우
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_fs::init())
        .manage(DownloadState::default())
        .manage(EmbeddingState::default())
        .manage(ConversionState::default())
        .manage(VideoServerState::default())
        .invoke_handler(tauri::generate_handler![
            get_debug_info,
            list_videos,
            list_channels,
            add_channel,
            remove_channel,
            toggle_channel,
            download_videos,
            download_videos_with_progress,
            download_videos_with_progress_and_quality,
            download_videos_full_scan_with_progress,
            cancel_download,
            get_available_channels_for_embedding,
            create_embeddings_for_channels_with_progress,
            cancel_embedding,
            create_embeddings,
            create_embeddings_with_progress,
            vector_search,
            ask_rag,
            ask_ai_universal_with_progress,
            get_available_channels_for_ai,
            get_channel_prompt,
            auto_generate_channel_prompt,
            get_channel_analysis,
            batch_generate_prompts,
            save_channel_prompt,
            get_prompt_versions,
            get_prompt_status,
            check_integrity,
            check_integrity_with_progress,
            get_app_status,
            get_recent_videos_by_channel,
            get_config,
            get_project_root_path,
            start_video_server,
            stop_video_server,
            get_video_server_status,
            get_video_url,
            open_in_system_player,
            convert_video_file,
            cancel_conversion,
            get_conversion_status
        ])
        .setup(|app| {
            let window = app.get_webview_window("main").unwrap();
            window.show().unwrap();
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
