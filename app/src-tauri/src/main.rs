#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::{command, Builder};
use std::fs;
use std::path::PathBuf;
use std::process::Command;

#[command]
fn list_videos() -> Result<Vec<VideoInfo>, String> {
    let root = PathBuf::from("../vault/10_videos");
    let mut videos = Vec::new();
    if root.exists() {
        for entry in fs::read_dir(root).map_err(|e| e.to_string())? {
            let entry = entry.map_err(|e| e.to_string())?;
            let path = entry.path();
            if path.is_dir() {
                collect_videos(&path, &mut videos)?;
            }
        }
    }
    Ok(videos)
}

fn collect_videos(dir: &PathBuf, videos: &mut Vec<VideoInfo>) -> Result<(), String> {
    for entry in fs::read_dir(dir).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let path = entry.path();
        if path.is_dir() {
            collect_videos(&path, videos)?;
        } else if path.file_name().map(|n| n == "video.mp4").unwrap_or(false) {
            let captions = path.parent().unwrap().join("captions.md");
            videos.push(VideoInfo {
                video_path: path.to_string_lossy().to_string(),
                captions_path: captions.to_string_lossy().to_string(),
            });
        }
    }
    Ok(())
}

#[derive(serde::Serialize)]
struct VideoInfo {
    video_path: String,
    captions_path: String,
}

#[command]
fn ask_rag(query: String) -> Result<String, String> {
    let output = Command::new("python")
        .arg("vault/90_indices/rag.py")
        .arg(query)
        .output()
        .map_err(|e| e.to_string())?;
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        Err(String::from_utf8_lossy(&output.stderr).to_string())
    }
}

fn main() {
    Builder::default()
        .invoke_handler(tauri::generate_handler![list_videos, ask_rag])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
