#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::command;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::io::{Write, BufRead, BufReader};
use std::env;
use std::collections::HashMap;
use tauri::{Emitter, Window, State};
use urlencoding::decode;
use regex::Regex;
use std::sync::{Arc, atomic::{AtomicBool, Ordering}};
use std::sync::Mutex;

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

// Y-Data-House 및 yt-dlp 출력 파싱
fn parse_ydh_output(line: &str) -> (f32, String, String) {
    // yt-dlp 다운로드 진행률 파싱: [download] 15.2% of 125.45MiB at 1.23MiB/s ETA 01:23
    if let Some(captures) = Regex::new(r"\[download\]\s+(\d+\.?\d*)%").unwrap().captures(line) {
        if let Some(percent_match) = captures.get(1) {
            if let Ok(percent) = percent_match.as_str().parse::<f32>() {
                let status_msg = format!("📥 다운로드 중... {}%", percent as i32);
                return (percent, String::new(), status_msg);
            }
        }
    }
    
    // 비디오 제목 추출: [youtube] abc123: Downloading video title
    if let Some(captures) = Regex::new(r"\[youtube\] [^:]+: (.+)").unwrap().captures(line) {
        if let Some(title_match) = captures.get(1) {
            let title = title_match.as_str().to_string();
            let status_msg = format!("🎥 {}", title);
            return (-1.0, title, status_msg);
        }
    }
    
    // Y-Data-House 로그 메시지 파싱
    if line.contains("📺") || line.contains("🎬") || line.contains("📝") {
        return (-1.0, String::new(), line.to_string());
    }
    
    // 다운로드 완료 메시지
    if line.contains("has already been downloaded") {
        return (100.0, String::new(), "✅ 이미 다운로드됨".to_string());
    }
    
    // 기본값
    (-1.0, String::new(), String::new())
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
    
    // 현재 실행 중인 프로세스 종료
    if let Ok(mut process_guard) = state.current_process.lock() {
        if let Some(mut child) = process_guard.take() {
            if let Err(e) = child.kill() {
                eprintln!("프로세스 종료 실패: {}", e);
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
    let venv_python = project_root.join("venv").join("bin").join("python");
    if !venv_python.exists() {
        return Err(format!("Python 가상환경이 설정되지 않았습니다: {}", venv_python.display()));
    }
    
    // 다운로드 시작 시 중단 플래그 초기화
    state.is_cancelled.store(false, Ordering::SeqCst);
    
    let mut results = Vec::new();
    let total_channels = enabled_channels.len() as u32;
    
    // 🔥 FIXED: 전체 비디오 수를 동적으로 계산
    let mut total_videos_processed = 0u32;
    let mut total_videos_downloaded = 0u32;
    
    for (index, channel) in enabled_channels.iter().enumerate() {
        // 중단 신호 확인
        if state.is_cancelled.load(Ordering::SeqCst) {
            let cancel_progress = DownloadProgress {
                channel: "전체".to_string(),
                status: "중단됨".to_string(),
                progress: (index as f32 / total_channels as f32) * 100.0,
                current_video: "사용자 요청으로 중단".to_string(),
                total_videos: total_videos_processed,
                completed_videos: total_videos_downloaded,
                log_message: "🛑 다운로드가 사용자 요청으로 중단되었습니다".to_string(),
            };
            let _ = window.emit("download-progress", &cancel_progress);
            return Ok("다운로드가 중단되었습니다".to_string());
        }
        // 진행 상황 업데이트
        let progress = DownloadProgress {
            channel: channel.name.clone(),
            status: "분석 중".to_string(),
            progress: (index as f32 / total_channels as f32) * 100.0,
            current_video: format!("채널 분석: {}", channel.name),
            total_videos: 0, // 아직 알 수 없음
            completed_videos: total_videos_downloaded,
            log_message: format!("📺 {} 채널 분석 시작...", channel.name),
        };
        
        // 프론트엔드에 진행 상황 전송
        let _ = window.emit("download-progress", &progress);
        
        // Python 명령어 실행 (실시간 출력 캡처)
        let child = Command::new(&venv_python)
            .args(&["-m", "ydh", "ingest", &channel.url])
            .current_dir(&project_root)
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
        
        // 프로세스를 다시 가져오기 (소유권 문제 해결)
        let mut child = if let Ok(mut process_guard) = state.current_process.lock() {
            process_guard.take().unwrap()
        } else {
            return Err("프로세스 접근 실패".to_string());
        };
        
        // 실시간 출력 읽기 (stdout과 stderr 동시 처리)
        let stdout = child.stdout.take();
        let stderr = child.stderr.take();
        
        // 🔥 NEW: 채널별 비디오 통계 추적
        let mut channel_total_videos = 0u32;
        let mut channel_downloaded_videos = 0u32;
        let mut current_video_progress = 0.0f32;
        
        // stdout과 stderr를 동시에 처리하는 스레드 생성
        let window_clone = window.clone();
        let channel_name = channel.name.clone();
        let channel_index = index;
        
        // state를 클론하여 각 스레드에서 사용
        let state_stdout = state.inner().clone();
        let state_stderr = state.inner().clone();
        
        std::thread::scope(|s| {
            // stdout 처리 스레드
            if let Some(stdout) = stdout {
                let window_stdout = window_clone.clone();
                let channel_name_stdout = channel_name.clone();
                s.spawn(move || {
                    let reader = BufReader::new(stdout);
                    for line in reader.lines() {
                        if let Ok(line) = line {
                            // 중단 신호 확인
                            if state_stdout.is_cancelled.load(Ordering::SeqCst) {
                                break;
                            }
                            // 🔥 FIXED: 실제 비디오 수 파싱
                            if line.contains("총") && line.contains("개 영상을 발견했습니다") {
                                if let Some(captures) = Regex::new(r"총 (\d+)개 영상을 발견했습니다").unwrap().captures(&line) {
                                    if let Some(count_match) = captures.get(1) {
                                        if let Ok(count) = count_match.as_str().parse::<u32>() {
                                            channel_total_videos = count;
                                        }
                                    }
                                }
                            }
                            
                            // 🔥 FIXED: 다운로드 완료/실패 카운트
                            if line.contains("다운로드 완료:") {
                                if let Some(captures) = Regex::new(r"다운로드 완료: (\d+)개 성공").unwrap().captures(&line) {
                                    if let Some(count_match) = captures.get(1) {
                                        if let Ok(count) = count_match.as_str().parse::<u32>() {
                                            channel_downloaded_videos = count;
                                        }
                                    }
                                }
                            }
                            

                            
                            let (parsed_progress, video_title, status_msg) = parse_ydh_output(&line);
                             
                             // 개별 비디오 진행률 업데이트
                             if parsed_progress >= 0.0 {
                                 current_video_progress = parsed_progress;
                             }
                             
                             // 전체 진행률 계산 개선
                             let base_progress = (channel_index as f32 / total_channels as f32) * 100.0;
                             let channel_progress_portion = if channel_total_videos > 0 {
                                 let completed_ratio = (channel_downloaded_videos as f32 + current_video_progress / 100.0) / channel_total_videos as f32;
                                 completed_ratio * (100.0 / total_channels as f32)
                             } else {
                                 (current_video_progress / 100.0) * (100.0 / total_channels as f32)
                             };
                             let total_progress = base_progress + channel_progress_portion;
                             
                             // 🔥 FIXED: 더 정확한 상태 판단
                             let status = if parsed_progress > 0.0 {
                                 "다운로드 중".to_string()
                             } else if line.contains("채널 영상 목록 수집") {
                                 "채널 분석 중".to_string()
                             } else if line.contains("다운로드 완료") {
                                 "완료".to_string()
                             } else if line.contains("모든 영상이 이미 다운로드") {
                                 "이미 완료".to_string()
                             } else if line.contains("Extracting") || line.contains("Downloading") {
                                 "영상 정보 수집 중".to_string()
                             } else {
                                 "진행 중".to_string()
                             };
                             
                             let progress_update = DownloadProgress {
                                 channel: channel_name_stdout.clone(),
                                 status,
                                 progress: total_progress.min(100.0),
                                 current_video: if video_title.is_empty() { 
                                     format!("채널: {}", channel_name_stdout) 
                                 } else { 
                                     video_title 
                                 },
                                 total_videos: channel_total_videos.max(1), // 최소 1개로 설정
                                 completed_videos: total_videos_downloaded + channel_downloaded_videos,
                                 log_message: if status_msg.is_empty() { line.clone() } else { status_msg },
                             };
                             
                             let _ = window_stdout.emit("download-progress", &progress_update);
                        }
                    }
                });
            }
            
            // stderr 처리 스레드 (WARNING/INFO 레벨은 오류가 아님)
            if let Some(stderr) = stderr {
                let window_stderr = window_clone.clone();
                let channel_name_stderr = channel_name.clone();
                s.spawn(move || {
                    let reader = BufReader::new(stderr);
                    for line in reader.lines() {
                        if let Ok(line) = line {
                            // 중단 신호 확인
                            if state_stderr.is_cancelled.load(Ordering::SeqCst) {
                                break;
                            }
                            // 🔥 FIXED: 실제 오류만 "오류" 상태로 처리
                            let is_real_error = line.contains("ERROR") || line.contains("CRITICAL") || 
                                               line.contains("Failed") || line.contains("Exception");
                            
                            let status = if is_real_error {
                                "오류"
                            } else {
                                "진행 중" // WARNING/INFO는 정상 진행으로 처리
                            };
                            
                            let (_parsed_progress, _video_title, status_msg) = parse_ydh_output(&line);
                             
                             // 모든 stderr 로그를 전송 (오류와 정보 구분)
                             let log_prefix = if is_real_error { "❌" } else { "⚠️" };
                             let log_progress = DownloadProgress {
                                 channel: channel_name_stderr.clone(),
                                 status: status.to_string(),
                                 progress: (channel_index as f32 / total_channels as f32) * 100.0,
                                 current_video: format!("채널: {}", channel_name_stderr),
                                 total_videos: channel_total_videos.max(1),
                                 completed_videos: total_videos_downloaded,
                                 log_message: if status_msg.is_empty() { 
                                     format!("{} {}", log_prefix, line) 
                                 } else { 
                                     format!("{} {}", log_prefix, status_msg) 
                                 },
                             };
                             
                             let _ = window_stderr.emit("download-progress", &log_progress);
                        }
                    }
                });
            }
        });
        
        // 프로세스 완료 대기 (중단 신호 확인하면서)
        let output = if state.is_cancelled.load(Ordering::SeqCst) {
            // 중단된 경우 프로세스 종료 후 결과 반환
            if let Err(e) = child.kill() {
                eprintln!("프로세스 종료 실패: {}", e);
            }
            return Ok("다운로드가 중단되었습니다".to_string());
        } else {
            child.wait_with_output().map_err(|e| e.to_string())?
        };
        
        // 🔥 FIXED: 채널별 통계 업데이트
        total_videos_processed += channel_total_videos;
        total_videos_downloaded += channel_downloaded_videos;
        
        if output.status.success() {
            results.push(format!("✅ {}: 성공 ({}/{}개)", channel.name, channel_downloaded_videos, channel_total_videos));
            let final_progress = DownloadProgress {
                channel: channel.name.clone(),
                status: "완료".to_string(),
                progress: ((index + 1) as f32 / total_channels as f32) * 100.0,
                current_video: format!("채널: {}", channel.name),
                total_videos: channel_total_videos,
                completed_videos: channel_downloaded_videos,
                log_message: format!("✅ {} 채널 다운로드 완료! ({}/{}개)", channel.name, channel_downloaded_videos, channel_total_videos),
            };
            let _ = window.emit("download-progress", &final_progress);
        } else {
            let error = String::from_utf8_lossy(&output.stderr);
            results.push(format!("❌ {}: {}", channel.name, error));
            let error_progress = DownloadProgress {
                channel: channel.name.clone(),
                status: "실패".to_string(),
                progress: ((index + 1) as f32 / total_channels as f32) * 100.0,
                current_video: format!("채널: {}", channel.name),
                total_videos: channel_total_videos,
                completed_videos: channel_downloaded_videos,
                log_message: format!("❌ {} 채널 다운로드 실패: {}", channel.name, error),
            };
            let _ = window.emit("download-progress", &error_progress);
        }
    }
    
    // 최종 완료 메시지
    let final_progress = DownloadProgress {
        channel: "전체".to_string(),
        status: "완료".to_string(),
        progress: 100.0,
        current_video: "모든 채널".to_string(),
        total_videos: total_videos_processed,
        completed_videos: total_videos_downloaded,
        log_message: format!("🎉 모든 채널 다운로드 완료! (총 {}/{}개)", total_videos_downloaded, total_videos_processed),
    };
    let _ = window.emit("download-progress", &final_progress);
    
    Ok(results.join("\n"))
}

// 기존 다운로드 함수 (호환성 유지)
#[command]
async fn download_videos() -> Result<String, String> {
    let channels = list_channels()?;
    let enabled_channels: Vec<_> = channels.into_iter().filter(|c| c.enabled).collect();
    
    if enabled_channels.is_empty() {
        return Err("활성화된 채널이 없습니다".to_string());
    }
    
    // Python 가상환경 확인
    let project_root = get_project_root();
    let venv_python = project_root.join("venv").join("bin").join("python");
    if !venv_python.exists() {
        return Err(format!("Python 가상환경이 설정되지 않았습니다: {}", venv_python.display()));
    }
    
    let mut results = Vec::new();
    
    for channel in enabled_channels {
        let output = Command::new(&venv_python)
            .args(&["-m", "ydh", "ingest", &channel.url])
            .current_dir(&project_root)
            .output()
            .map_err(|e| e.to_string())?;
        
        if output.status.success() {
            results.push(format!("✅ {}: 성공", channel.name));
        } else {
            let error = String::from_utf8_lossy(&output.stderr);
            results.push(format!("❌ {}: {}", channel.name, error));
        }
    }
    
    Ok(results.join("\n"))
}

// 벡터 임베딩 생성 (진행 상황 포함)
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
    
    // 진행률 업데이트 (25% - 시작)
    let progress_25 = DownloadProgress {
        channel: "벡터 임베딩".to_string(),
        status: "시작".to_string(),
        progress: 25.0,
        current_video: "스크립트 실행 중...".to_string(),
        total_videos: 1,
        completed_videos: 0,
        log_message: "🧠 벡터 임베딩 스크립트 실행 중...".to_string(),
    };
    let _ = window.emit("embedding-progress", &progress_25);
    
    // 진행률 업데이트 (50% - 처리 중)
    let progress_50 = DownloadProgress {
        channel: "벡터 임베딩".to_string(),
        status: "처리 중".to_string(),
        progress: 50.0,
        current_video: "임베딩 생성 중...".to_string(),
        total_videos: 1,
        completed_videos: 0,
        log_message: "📊 비디오 자막 분석 및 임베딩 생성 중...".to_string(),
    };
    let _ = window.emit("embedding-progress", &progress_50);
    
    // Python 스크립트 실행
    let output = Command::new(&venv_python)
        .arg(&embed_script)
        .current_dir(&project_root)
        .env("PYTHONUNBUFFERED", "1")
        .output()
        .map_err(|e| e.to_string())?;
    
    // 진행률 업데이트 (75% - 거의 완료)
    let progress_75 = DownloadProgress {
        channel: "벡터 임베딩".to_string(),
        status: "완료 중".to_string(),
        progress: 75.0,
        current_video: "임베딩 저장 중...".to_string(),
        total_videos: 1,
        completed_videos: 0,
        log_message: "💾 ChromaDB에 벡터 임베딩 저장 중...".to_string(),
    };
    let _ = window.emit("embedding-progress", &progress_75);
    
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
    
    // Python 명령어 실행
    let output = Command::new(&venv_python)
        .args(&["-m", "ydh", "config-validate"])
        .current_dir(&project_root)
        .env("PYTHONUNBUFFERED", "1")
        .output()
        .map_err(|e| e.to_string())?;
    
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
    
    let output = Command::new(&venv_python)
        .args(&["-m", "ydh", "config-validate"])
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



fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_fs::init())
        .manage(DownloadState::default())
        .invoke_handler(tauri::generate_handler![
            get_debug_info,
            list_videos,
            list_channels,
            add_channel,
            remove_channel,
            toggle_channel,
            download_videos,
            download_videos_with_progress,
            cancel_download,
            create_embeddings,
            create_embeddings_with_progress,
            vector_search,
            ask_rag,
            check_integrity,
            check_integrity_with_progress,
            get_app_status,
            get_recent_videos_by_channel,
            get_config,
            get_project_root_path
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
